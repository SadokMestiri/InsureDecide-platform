"""
InsureDecide — Service Clients à Risque
"""

import os
import logging
import psycopg2
from decimal import Decimal
from typing import Optional
from app.denodo_client import get_contrats_unifies, get_sinistres_enrichis, get_client_360

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://insuredecide_user:insuredecide_pass@postgres:5432/insuredecide")

TABLES = {
    "Automobile": ("contrats_automobile", True),   # (table, has_gouvernorat)
    "Vie":        ("contrats_vie",        False),
    "Immobilier": ("contrats_immobilier", True),
}

def _clean(val):
    if isinstance(val, Decimal): return float(val)
    return val or 0


def _to_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def _norm_sinistre(row: dict) -> dict:
    return {
        "sinistre_id": row.get("sinistre_id"),
        "client_id": str(row.get("client_id")) if row.get("client_id") is not None else "",
        "contrat_id": row.get("contrat_id"),
        "departement": row.get("departement") or "",
        "gouvernorat": row.get("gouvernorat") or "",
        "type": row.get("type_sinistre") or row.get("type") or "",
        "date": str(row.get("date_sinistre") or row.get("date") or ""),
        "cout": _to_float(row.get("cout_sinistre_tnd", row.get("cout", 0))),
        "fraude": bool(row.get("suspicion_fraude") or row.get("fraude")),
        "nom": row.get("nom") or "",
        "prenom": row.get("prenom") or "",
        "age": row.get("age") if row.get("age") is not None else None,
    }


def _norm_contrat(row: dict) -> dict:
    return {
        "contrat_id": row.get("contrat_id"),
        "client_id": str(row.get("client_id")) if row.get("client_id") is not None else "",
        "departement": row.get("departement") or "",
        "prime": _to_float(row.get("prime_annuelle_tnd", row.get("prime", 0))),
        "statut": row.get("statut") or "",
        "gouvernorat": row.get("gouvernorat") or "",
    }

def _score(nb_sin, cout_total, nb_fraudes, prime_annuelle):
    score_sin    = min(nb_sin    / 10   * 35, 35)
    score_cout   = min(cout_total/ 50000* 25, 25)
    score_fraude = min(nb_fraudes* 12.5,      25)
    ratio_cp     = (cout_total / prime_annuelle) if prime_annuelle > 0 else 0
    score_ratio  = min(ratio_cp * 7.5,        15)
    return round(min(score_sin + score_cout + score_fraude + score_ratio, 100), 1)

def _action(score):
    if score >= 75: return {"action":"Résilier le contrat",     "color":"#dc2626","bg":"#fef2f2","icon":"🚫"}
    if score >= 50: return {"action":"Augmenter la prime +20%", "color":"#f97316","bg":"#fff7ed","icon":"📈"}
    if score >= 30: return {"action":"Surveiller",              "color":"#f59e0b","bg":"#fffbeb","icon":"👁️"}
    return             {"action":"RAS",                         "color":"#10b981","bg":"#ecfdf5","icon":"✅"}


def get_clients_risque(
    departement: Optional[str] = None,
    gouvernorat: Optional[str] = None,
    seuil_sinistres: int = 2,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    # Denodo first
    try:
        contrats_res = get_contrats_unifies(None)
        sin_res = get_sinistres_enrichis(None, 5000)
        if contrats_res.get("source") == "denodo" and sin_res.get("source") == "denodo":
            contrats = [_norm_contrat(c) for c in (contrats_res.get("data") or [])]
            sinistres = [_norm_sinistre(s) for s in (sin_res.get("data") or [])]

            contrats = [c for c in contrats if str(c.get("statut", "")).lower() == "actif"]
            if departement:
                contrats = [c for c in contrats if c["departement"] == departement]

            contrat_by_id = {str(c["contrat_id"]): c for c in contrats if c.get("contrat_id") is not None}
            by_client = {}

            for c in contrats:
                cid = c["client_id"]
                if not cid:
                    continue
                by_client.setdefault(cid, {
                    "client_id": cid,
                    "nom": "",
                    "gouvernorat": c["gouvernorat"],
                    "age": None,
                    "contrats": [],
                    "nb_sinistres": 0,
                    "cout_total": 0.0,
                    "nb_fraudes": 0,
                    "prime_totale": 0.0,
                    "departements": [],
                })
                by_client[cid]["contrats"].append(c["contrat_id"])
                by_client[cid]["prime_totale"] += c["prime"]
                if c["departement"] and c["departement"] not in by_client[cid]["departements"]:
                    by_client[cid]["departements"].append(c["departement"])

            for s in sinistres:
                cid = s["client_id"]
                c_match = contrat_by_id.get(str(s.get("contrat_id")))
                if not cid and c_match:
                    cid = c_match["client_id"]
                if not cid or cid not in by_client:
                    continue
                if departement and s["departement"] and s["departement"] != departement:
                    continue
                if gouvernorat:
                    gov = s["gouvernorat"] or by_client[cid].get("gouvernorat") or ""
                    if gov.lower() != gouvernorat.lower():
                        continue

                by_client[cid]["nb_sinistres"] += 1
                by_client[cid]["cout_total"] += s["cout"]
                by_client[cid]["nb_fraudes"] += 1 if s["fraude"] else 0
                if not by_client[cid]["gouvernorat"] and s["gouvernorat"]:
                    by_client[cid]["gouvernorat"] = s["gouvernorat"]
                if not by_client[cid]["nom"] and (s["nom"] or s["prenom"]):
                    by_client[cid]["nom"] = f"{s['prenom']} {s['nom']}".strip()
                if by_client[cid]["age"] is None and s["age"] is not None:
                    by_client[cid]["age"] = s["age"]

            final = []
            for r in by_client.values():
                if r["nb_sinistres"] < seuil_sinistres:
                    continue
                if gouvernorat and (r.get("gouvernorat") or "").lower() != gouvernorat.lower():
                    continue
                score = _score(r["nb_sinistres"], r["cout_total"], r["nb_fraudes"], r["prime_totale"])
                rec = _action(score)
                final.append({
                    **r,
                    "nom": r["nom"] or f"Client {r['client_id']}",
                    "score": score,
                    "action": rec["action"],
                    "action_color": rec["color"],
                    "action_bg": rec["bg"],
                    "action_icon": rec["icon"],
                    "cout_total": round(r["cout_total"], 0),
                    "prime_totale": round(r["prime_totale"], 0),
                    "ratio_cout_prime": round(r["cout_total"] / r["prime_totale"], 2) if r["prime_totale"] > 0 else 0,
                })

            if final:
                final.sort(key=lambda x: x["score"], reverse=True)
                total = len(final)
                resilier = sum(1 for c in final if c["score"] >= 75)
                augmenter = sum(1 for c in final if 50 <= c["score"] < 75)
                surveiller = sum(1 for c in final if 30 <= c["score"] < 50)
                return {
                    "clients": final[offset:offset + limit],
                    "total": total,
                    "source": "denodo",
                    "stats": {
                        "resilier": resilier,
                        "augmenter": augmenter,
                        "surveiller": surveiller,
                        "ras": total - resilier - augmenter - surveiller,
                    },
                }
    except Exception as e:
        logger.warning(f"[Denodo] risque clients fallback PostgreSQL: {e}")

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    # Sélectionner les tables à interroger
    if departement and departement in TABLES:
        tables_to_query = {departement: TABLES[departement]}
    else:
        tables_to_query = TABLES

    results = {}

    for dept_name, (table, has_gov) in tables_to_query.items():
        gov_select = "c.gouvernorat" if has_gov else "NULL::varchar"
        gov_filter = "AND c.gouvernorat = %(gov)s" if (has_gov and gouvernorat) else ""
        gov_group  = ", c.gouvernorat" if has_gov else ""

        sql = f"""
            SELECT
                cl.client_id,
                cl.prenom || ' ' || cl.nom AS nom_complet,
                {gov_select}               AS gouvernorat,
                cl.age,
                c.contrat_id,
                c.prime_annuelle_tnd,
                COUNT(s.sinistre_id)        AS nb_sinistres,
                COALESCE(SUM(s.cout_sinistre_tnd), 0) AS cout_total,
                COUNT(CASE WHEN s.suspicion_fraude THEN 1 END) AS nb_fraudes
            FROM clients cl
            JOIN {table} c ON c.client_id = cl.client_id
            LEFT JOIN sinistres s ON s.contrat_id = c.contrat_id
            WHERE c.statut = %(statut)s
            {gov_filter}
            GROUP BY cl.client_id, cl.prenom, cl.nom, cl.age,
                     c.contrat_id, c.prime_annuelle_tnd
                     {gov_group}
            HAVING COUNT(s.sinistre_id) >= %(seuil)s
            ORDER BY COUNT(s.sinistre_id) DESC, COALESCE(SUM(s.cout_sinistre_tnd),0) DESC
        """
        cur.execute(sql, {"gov": gouvernorat, "seuil": seuil_sinistres, "statut": "Actif"})

        for row in cur.fetchall():
            cid, nom, gov, age, contrat_id, prime, nb_sin, cout_tot, nb_fraudes = row
            prime    = _clean(prime)
            cout_tot = _clean(cout_tot)
            nb_sin   = int(nb_sin)
            nb_fraudes = int(nb_fraudes)

            if cid not in results:
                results[cid] = {
                    "client_id":    cid,
                    "nom":          nom,
                    "gouvernorat":  gov or "",
                    "age":          age,
                    "contrats":     [],
                    "nb_sinistres": 0,
                    "cout_total":   0.0,
                    "nb_fraudes":   0,
                    "prime_totale": 0.0,
                    "departements": [],
                }

            results[cid]["contrats"].append(contrat_id)
            results[cid]["nb_sinistres"] += nb_sin
            results[cid]["cout_total"]   += cout_tot
            results[cid]["nb_fraudes"]   += nb_fraudes
            results[cid]["prime_totale"] += prime
            if dept_name not in results[cid]["departements"]:
                results[cid]["departements"].append(dept_name)
            # Mettre à jour gouvernorat si vide
            if not results[cid]["gouvernorat"] and gov:
                results[cid]["gouvernorat"] = gov

    final = []
    for r in results.values():
        score = _score(r["nb_sinistres"], r["cout_total"], r["nb_fraudes"], r["prime_totale"])
        rec   = _action(score)
        final.append({
            **r,
            "score":          score,
            "action":         rec["action"],
            "action_color":   rec["color"],
            "action_bg":      rec["bg"],
            "action_icon":    rec["icon"],
            "cout_total":     round(r["cout_total"], 0),
            "prime_totale":   round(r["prime_totale"], 0),
            "ratio_cout_prime": round(r["cout_total"] / r["prime_totale"], 2) if r["prime_totale"] > 0 else 0,
        })

    final.sort(key=lambda x: x["score"], reverse=True)

    total      = len(final)
    resilier   = sum(1 for c in final if c["score"] >= 75)
    augmenter  = sum(1 for c in final if 50 <= c["score"] < 75)
    surveiller = sum(1 for c in final if 30 <= c["score"] < 50)

    cur.close()
    conn.close()

    return {
        "clients": final[offset:offset+limit],
        "total":   total,
        "source": "postgresql_direct",
        "stats": {
            "resilier":   resilier,
            "augmenter":  augmenter,
            "surveiller": surveiller,
            "ras":        total - resilier - augmenter - surveiller,
        },
    }


def get_client_detail(client_id: str) -> dict:
    # Denodo first
    try:
        sin_res = get_sinistres_enrichis(None, 5000)
        contrats_res = get_contrats_unifies(int(client_id) if str(client_id).isdigit() else None)
        client360 = get_client_360(client_id)

        if sin_res.get("source") == "denodo" and contrats_res.get("source") == "denodo":
            sinistres_all = [_norm_sinistre(s) for s in (sin_res.get("data") or [])]
            sinistres = [s for s in sinistres_all if s["client_id"] == str(client_id)]

            contrats_all = [_norm_contrat(c) for c in (contrats_res.get("data") or [])]
            contrats = [c for c in contrats_all if c["client_id"] == str(client_id) and str(c.get("statut", "")).lower() == "actif"]

            client_data = client360.get("data") if isinstance(client360, dict) else None
            nom = ""
            if client_data:
                nom = (f"{client_data.get('prenom', '')} {client_data.get('nom', '')}").strip()
            if not nom and sinistres:
                nom = f"{sinistres[0].get('prenom', '')} {sinistres[0].get('nom', '')}".strip()

            age = (client_data or {}).get("age")
            gouvernorat = (client_data or {}).get("gouvernorat") or (sinistres[0].get("gouvernorat") if sinistres else "")

            sinistres_fmt = [
                {
                    "id": s["sinistre_id"],
                    "contrat": s["contrat_id"],
                    "dept": s["departement"],
                    "type": s["type"],
                    "date": s["date"],
                    "cout": round(s["cout"], 0),
                    "statut": "",
                    "fraude": bool(s["fraude"]),
                }
                for s in sorted(sinistres, key=lambda x: x["date"], reverse=True)
            ]
            contrats_fmt = [
                {
                    "dept": c["departement"],
                    "id": c["contrat_id"],
                    "prime": round(c["prime"], 0),
                    "statut": c["statut"],
                    "gouvernorat": c["gouvernorat"],
                }
                for c in contrats
            ]

            nb_sin = len(sinistres_fmt)
            cout_total = sum(s["cout"] for s in sinistres_fmt)
            nb_fraudes = sum(1 for s in sinistres_fmt if s["fraude"])
            prime_tot = sum(c["prime"] for c in contrats_fmt)
            score = _score(nb_sin, cout_total, nb_fraudes, prime_tot)
            rec = _action(score)

            if sinistres_fmt or contrats_fmt or client_data:
                return {
                    "client_id": str(client_id),
                    "nom": nom or f"Client {client_id}",
                    "age": age,
                    "gouvernorat": gouvernorat or "",
                    "profession": (client_data or {}).get("profession"),
                    "revenu": _clean((client_data or {}).get("revenu_mensuel_tnd", 0)),
                    "date_inscr": str((client_data or {}).get("date_inscription", "")),
                    "contrats": contrats_fmt,
                    "sinistres": sinistres_fmt,
                    "nb_sinistres": nb_sin,
                    "cout_total": cout_total,
                    "nb_fraudes": nb_fraudes,
                    "score": score,
                    "action": rec["action"],
                    "action_color": rec["color"],
                    "action_bg": rec["bg"],
                    "action_icon": rec["icon"],
                    "source": "denodo",
                }
    except Exception as e:
        logger.warning(f"[Denodo] client detail fallback PostgreSQL: {e}")

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    cur.execute("""
        SELECT client_id, prenom || ' ' || nom, age, gouvernorat,
               profession, revenu_mensuel_tnd, date_inscription
        FROM clients WHERE client_id = %s
    """, [client_id])
    row = cur.fetchone()
    if not row:
        return {}
    cid, nom, age, gov, prof, revenu, date_inscr = row

    cur.execute("""
        SELECT sinistre_id, contrat_id, departement, type_sinistre,
               date_sinistre, cout_sinistre_tnd, statut, suspicion_fraude
        FROM sinistres WHERE client_id = %s
        ORDER BY date_sinistre DESC
    """, [client_id])
    sinistres = [
        {"id":r[0],"contrat":r[1],"dept":r[2],"type":r[3],
         "date":str(r[4]),"cout":round(_clean(r[5]),0),
         "statut":r[6],"fraude":bool(r[7])}
        for r in cur.fetchall()
    ]

    cur.execute("""
        SELECT 'Automobile', contrat_id, prime_annuelle_tnd, statut, gouvernorat
        FROM contrats_automobile WHERE client_id = %s AND statut = 'Actif'
        UNION ALL
        SELECT 'Vie', contrat_id, prime_annuelle_tnd, statut, NULL
        FROM contrats_vie WHERE client_id = %s AND statut = 'Actif'
        UNION ALL
        SELECT 'Immobilier', contrat_id, prime_annuelle_tnd, statut, gouvernorat
        FROM contrats_immobilier WHERE client_id = %s AND statut = 'Actif'
    """, [client_id, client_id, client_id])
    contrats = [
        {"dept":r[0],"id":r[1],"prime":round(_clean(r[2]),0),"statut":r[3],"gouvernorat":r[4] or ""}
        for r in cur.fetchall()
    ]

    cur.close()
    conn.close()

    nb_sin     = len(sinistres)
    cout_total = sum(s["cout"] for s in sinistres)
    nb_fraudes = sum(1 for s in sinistres if s["fraude"])
    prime_tot  = sum(c["prime"] for c in contrats)
    score      = _score(nb_sin, cout_total, nb_fraudes, prime_tot)
    rec        = _action(score)

    return {
        "client_id":    cid,
        "nom":          nom,
        "age":          age,
        "gouvernorat":  gov or "",
        "profession":   prof,
        "revenu":       round(_clean(revenu), 0),
        "date_inscr":   str(date_inscr),
        "contrats":     contrats,
        "sinistres":    sinistres,
        "nb_sinistres": nb_sin,
        "cout_total":   cout_total,
        "nb_fraudes":   nb_fraudes,
        "score":        score,
        "action":       rec["action"],
        "action_color": rec["color"],
        "action_bg":    rec["bg"],
        "action_icon":  rec["icon"],
        "source":       "postgresql_direct",
    }