"""
InsureDecide — Service Clients à Risque
"""

import os
import logging
import psycopg2
from decimal import Decimal
from typing import Optional

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
        "stats": {
            "resilier":   resilier,
            "augmenter":  augmenter,
            "surveiller": surveiller,
            "ras":        total - resilier - augmenter - surveiller,
        },
    }


def get_client_detail(client_id: str) -> dict:
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
    }