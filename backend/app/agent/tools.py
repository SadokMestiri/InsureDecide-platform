"""
InsureDecide — Outils LangGraph
Trois outils que les sous-agents peuvent appeler :
  - kpi_tool    : requête SQL directe sur PostgreSQL
  - rag_tool    : recherche sémantique dans Qdrant
  - alerte_tool : récupère les alertes actives
"""

import os
import logging
import re
from typing import Optional
from langchain_core.tools import tool
from qdrant_client import QdrantClient
from fastembed import TextEmbedding
import psycopg2
from app.denodo_client import get_kpis_enrichis

logger = logging.getLogger(__name__)

QDRANT_URL   = os.getenv("QDRANT_URL",   "http://qdrant:6333")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://insuredecide_user:insuredecide_pass@postgres:5432/insuredecide")
EMBED_MODEL  = "BAAI/bge-small-en-v1.5"

DEPARTEMENTS = ["Automobile", "Vie", "Immobilier"]
INDICATEURS_FORECAST = [
    "primes_acquises_tnd",
    "cout_sinistres_tnd",
    "nb_sinistres",
    "ratio_combine_pct",
]

# Singletons (initialisés une fois au démarrage)
_qdrant_client: Optional[QdrantClient]  = None
_embedder:      Optional[TextEmbedding] = None


def get_qdrant() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=QDRANT_URL)
    return _qdrant_client


def get_embedder() -> TextEmbedding:
    global _embedder
    if _embedder is None:
        _embedder = TextEmbedding(model_name=EMBED_MODEL)
    return _embedder


def get_pg():
    return psycopg2.connect(DATABASE_URL)


def _denodo_kpi_rows():
    try:
        result = get_kpis_enrichis(None)
        if result.get("source") != "denodo":
            return []
        rows = result.get("data") or []
        return [r for r in rows if r.get("departement")]
    except Exception as e:
        logger.warning(f"[Denodo] agent fallback PostgreSQL: {e}")
        return []


def _detect_departement(text: str) -> Optional[str]:
    q = (text or "").lower()
    if "auto" in q or "automobile" in q:
        return "Automobile"
    if "vie" in q:
        return "Vie"
    if "immo" in q or "immobilier" in q:
        return "Immobilier"
    return None


def _detect_forecast_indicateur(text: str) -> str:
    q = (text or "").lower()
    if "sinistre" in q and ("nb" in q or "nombre" in q):
        return "nb_sinistres"
    if "ratio" in q or "combine" in q:
        return "ratio_combine_pct"
    if "coût" in q or "cout" in q:
        return "cout_sinistres_tnd"
    return "primes_acquises_tnd"


def _detect_horizon_mois(text: str, default: int = 6) -> int:
    q = (text or "").lower()
    for n in [3, 6, 9, 12, 18, 24]:
        if f"{n} mois" in q or f"{n}mois" in q:
            return n
    if "trimestre" in q:
        return 3
    if "an" in q or "année" in q or "annee" in q:
        return 12
    return default


def _detect_n_clusters(text: str, default: int = 4) -> int:
    q = (text or "").lower()
    for n in [2, 3, 4, 5, 6, 7, 8]:
        if f"{n} cluster" in q or f"{n} segment" in q:
            return n
    return default


def _detect_top_n(text: str, default: int = 5, max_n: int = 20) -> int:
    q = (text or "").lower()
    m = re.search(r"top\s*(\d{1,2})", q)
    if m:
        return max(1, min(max_n, int(m.group(1))))
    for n in [3, 5, 10, 15, 20]:
        if str(n) in q:
            return n
    return default


def _extract_year_month(text: str) -> tuple[Optional[int], Optional[int]]:
    q = (text or "")
    m = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", q)
    if m:
        return int(m.group(1)), int(m.group(2))
    y = re.search(r"\b(20\d{2})\b", q)
    if y:
        return int(y.group(1)), None
    return None, None


def run_sql_analytics(question: str) -> dict:
    q = (question or "").lower()

    # Cas 1: total clients (question volumétrique)
    is_total_clients_q = (
        ("client" in q or "clients" in q)
        and any(k in q for k in ["nombre", "combien", "total", "nb"])
        and "sinistre" not in q
    )
    if is_total_clients_q:
        dept = _detect_departement(question)
        conn = get_pg()
        cur = conn.cursor()
        if dept == "Automobile":
            cur.execute("SELECT COUNT(DISTINCT client_id)::int FROM contrats_automobile")
        elif dept == "Vie":
            cur.execute("SELECT COUNT(DISTINCT client_id)::int FROM contrats_vie")
        elif dept == "Immobilier":
            cur.execute("SELECT COUNT(DISTINCT client_id)::int FROM contrats_immobilier")
        else:
            cur.execute("SELECT COUNT(*)::int FROM clients")
        total_clients = int((cur.fetchone() or [0])[0] or 0)
        cur.close()
        conn.close()

        return {
            "status": "ok",
            "query_type": "total_clients",
            "scope": {
                "departement": dept or "Tous",
            },
            "rows": [{"metric": "Total Clients", "value": total_clients}],
            "top": {"metric": "Total Clients", "value": total_clients},
        }

    # Cas 2: top gouvernorat par sinistres
    if not ("sinistre" in q and "gouvernorat" in q):
        return {
            "status": "unsupported",
            "detail": "Intent SQL non supporté pour cette question.",
        }

    top_n = _detect_top_n(question, default=10)
    dept = _detect_departement(question)
    year, month = _extract_year_month(question)

    where = ["COALESCE(gouvernorat, '') <> ''"]
    params = []
    if dept:
        where.append("departement = %s")
        params.append(dept)
    if year is not None:
        where.append("EXTRACT(YEAR FROM date_sinistre) = %s")
        params.append(year)
    if month is not None:
        where.append("EXTRACT(MONTH FROM date_sinistre) = %s")
        params.append(month)

    sql = (
        "SELECT gouvernorat, COUNT(*)::int AS nb_sinistres, "
        "COALESCE(SUM(cout_sinistre_tnd),0)::numeric AS cout_total_tnd "
        "FROM sinistres "
        f"WHERE {' AND '.join(where)} "
        "GROUP BY gouvernorat "
        "ORDER BY nb_sinistres DESC, cout_total_tnd DESC "
        "LIMIT %s"
    )
    params.append(top_n)

    conn = get_pg()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    data = [
        {
            "gouvernorat": r[0],
            "nb_sinistres": int(r[1] or 0),
            "cout_total_tnd": float(r[2] or 0),
        }
        for r in rows
    ]

    total = sum(x["nb_sinistres"] for x in data) if data else 0
    for x in data:
        x["part_pct"] = round((x["nb_sinistres"] / total * 100), 1) if total else 0.0

    return {
        "status": "ok" if data else "empty",
        "query_type": "top_gouvernorat_sinistres",
        "scope": {
            "departement": dept or "Tous",
            "year": year,
            "month": month,
            "top_n": top_n,
        },
        "rows": data,
        "top": data[0] if data else None,
    }


def _extract_client_id(text: str) -> Optional[str]:
    q = (text or "")
    m = re.search(r"\bCLT\d{3,}\b", q, flags=re.IGNORECASE)
    return m.group(0).upper() if m else None


def _extract_client_fullname(text: str) -> Optional[str]:
    q = (text or "").strip()
    if not q:
        return None
    # Capture patterns like "sinistres de Ali Ayari" or "d'Ali Ayari"
    m = re.search(r"(?:sinistres?\s+(?:de|d')|client\s+(?:de|d')|de|d')\s+([A-Za-zÀ-ÿ'\-]+\s+[A-Za-zÀ-ÿ'\-]+)", q, flags=re.IGNORECASE)
    if m:
        name = " ".join(part for part in m.group(1).strip().split() if part)
        return name.title()
    return None


def _extract_target_claim_count(text: str) -> Optional[int]:
    q = (text or "").lower()
    m = re.search(r"(\d{1,3})\s*sinistres?", q)
    if m:
        return int(m.group(1))
    return None


def is_specific_client_question(question: str) -> bool:
    q = (question or "").lower()
    if _extract_client_id(question):
        return True
    return (
        ("sinistre" in q or "client" in q)
        and (" de " in q or "d'" in q)
        and any(k in q for k in ["departement", "département", "quel", "dans quel", "repartition", "répartition", "combien"])
    )


def _resolve_client(question: str) -> dict:
    client_id = _extract_client_id(question)
    full_name = _extract_client_fullname(question)
    target_claims = _extract_target_claim_count(question)

    conn = get_pg()
    cur = conn.cursor()

    if client_id:
        cur.execute(
            """
            SELECT client_id, COALESCE(prenom, ''), COALESCE(nom, '')
            FROM clients
            WHERE client_id = %s
            LIMIT 1
            """,
            [client_id],
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"status": "not_found", "reason": f"Client ID introuvable: {client_id}"}
        return {
            "status": "ok",
            "client_id": row[0],
            "client_name": f"{row[1]} {row[2]}".strip() or row[0],
        }

    if full_name:
        cur.execute(
            """
            SELECT
                c.client_id,
                COALESCE(c.prenom, ''),
                COALESCE(c.nom, ''),
                COALESCE(s.nb_sinistres, 0) AS nb_sinistres
            FROM clients c
            LEFT JOIN (
                SELECT client_id, COUNT(*)::int AS nb_sinistres
                FROM sinistres
                GROUP BY client_id
            ) s ON s.client_id = c.client_id
            WHERE LOWER(TRIM(c.prenom || ' ' || c.nom)) = LOWER(%s)
            ORDER BY nb_sinistres DESC, c.client_id
            """,
            [full_name],
        )
        exact_rows = cur.fetchall()
        if exact_rows:
            if len(exact_rows) == 1:
                exact = exact_rows[0]
                cur.close()
                conn.close()
                return {
                    "status": "ok",
                    "client_id": exact[0],
                    "client_name": f"{exact[1]} {exact[2]}".strip() or exact[0],
                }

            # Homonymes: si la question précise un nombre de sinistres, choisir le meilleur match.
            if target_claims is not None:
                exact_rows = sorted(exact_rows, key=lambda x: abs(int(x[3] or 0) - target_claims))
                best = exact_rows[0]
                if int(best[3] or 0) == target_claims:
                    cur.close()
                    conn.close()
                    return {
                        "status": "ok",
                        "client_id": best[0],
                        "client_name": f"{best[1]} {best[2]}".strip() or best[0],
                    }

            # Sinon renvoyer l'ambiguïté explicitement.
            cur.close()
            conn.close()
            return {
                "status": "ambiguous",
                "query_name": full_name,
                "reason": "Plusieurs clients portent le même nom.",
                "candidates": [
                    {
                        "client_id": r[0],
                        "client_name": f"{r[1]} {r[2]}".strip() or r[0],
                        "nb_sinistres": int(r[3] or 0),
                    }
                    for r in exact_rows[:5]
                ],
            }

        cur.execute(
            """
            SELECT
                c.client_id,
                COALESCE(c.prenom, ''),
                COALESCE(c.nom, ''),
                COALESCE(s.nb_sinistres, 0) AS nb_sinistres,
                similarity(LOWER(TRIM(c.prenom || ' ' || c.nom)), LOWER(%s)) AS sim
            FROM clients c
            LEFT JOIN (
                SELECT client_id, COUNT(*)::int AS nb_sinistres
                FROM sinistres
                GROUP BY client_id
            ) s ON s.client_id = c.client_id
            WHERE LOWER(TRIM(c.prenom || ' ' || c.nom)) %% LOWER(%s)
            ORDER BY sim DESC, nb_sinistres DESC
            LIMIT 5
            """,
            [full_name, full_name],
        )
        candidates = cur.fetchall()
        cur.close()
        conn.close()
        if not candidates:
            return {"status": "not_found", "reason": f"Client introuvable: {full_name}"}

        if len(candidates) == 1:
            c = candidates[0]
            cur.close()
            return {
                "status": "ok",
                "client_id": c[0],
                "client_name": f"{c[1]} {c[2]}".strip() or c[0],
            }
        return {
            "status": "ambiguous",
            "query_name": full_name,
            "candidates": [
                {
                    "client_id": c[0],
                    "client_name": f"{c[1]} {c[2]}".strip() or c[0],
                    "nb_sinistres": int(c[3] or 0),
                }
                for c in candidates
            ],
        }

    cur.close()
    conn.close()
    return {"status": "not_found", "reason": "Aucun client explicite détecté dans la question."}


def get_client_claims_profile(question: str) -> dict:
    resolved = _resolve_client(question)
    if resolved.get("status") != "ok":
        return resolved

    client_id = resolved["client_id"]
    client_name = resolved["client_name"]

    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            departement,
            COUNT(*)::int AS nb_sinistres,
            COALESCE(SUM(cout_sinistre_tnd), 0)::numeric AS cout_total_tnd
        FROM sinistres
        WHERE client_id = %s
        GROUP BY departement
        ORDER BY nb_sinistres DESC, cout_total_tnd DESC
        """,
        [client_id],
    )
    dept_rows = cur.fetchall()

    cur.execute(
        """
        SELECT
            sinistre_id,
            departement,
            date_sinistre,
            type_sinistre,
            COALESCE(cout_sinistre_tnd, 0)::numeric AS cout_tnd,
            COALESCE(statut, '')
        FROM sinistres
        WHERE client_id = %s
        ORDER BY date_sinistre DESC NULLS LAST, cout_sinistre_tnd DESC
        LIMIT 20
        """,
        [client_id],
    )
    claims_rows = cur.fetchall()
    cur.close()
    conn.close()

    total_claims = sum(int(r[1] or 0) for r in dept_rows) if dept_rows else 0
    departements = [
        {
            "departement": r[0],
            "nb_sinistres": int(r[1] or 0),
            "cout_total_tnd": float(r[2] or 0),
            "part_pct": round((int(r[1] or 0) / total_claims * 100), 1) if total_claims else 0.0,
        }
        for r in dept_rows
    ]

    claims = [
        {
            "sinistre_id": r[0],
            "departement": r[1],
            "date_sinistre": str(r[2]) if r[2] is not None else None,
            "type_sinistre": r[3],
            "cout_tnd": float(r[4] or 0),
            "statut": r[5],
        }
        for r in claims_rows
    ]

    return {
        "status": "ok",
        "client_id": client_id,
        "client_name": client_name,
        "nb_sinistres_total": total_claims,
        "departements": departements,
        "sinistres": claims,
    }


def _get_clients_dept_breakdown(client_ids: list[str]) -> dict:
    ids = [str(x) for x in (client_ids or []) if x]
    if not ids:
        return {}

    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT client_id, departement, COUNT(*)::int AS nb
        FROM sinistres
        WHERE client_id = ANY(%s)
        GROUP BY client_id, departement
        ORDER BY client_id, nb DESC
        """,
        [ids],
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    out = {cid: [] for cid in ids}
    totals = {cid: 0 for cid in ids}
    for cid, dept, nb in rows:
        totals[cid] = totals.get(cid, 0) + int(nb or 0)
        out.setdefault(cid, []).append({"departement": dept, "nb_sinistres": int(nb or 0)})

    for cid in out.keys():
        total = totals.get(cid, 0)
        for d in out[cid]:
            d["part_pct"] = round((d["nb_sinistres"] / total * 100), 1) if total else 0.0
    return out


def get_top_clients_claims(departement: Optional[str] = None, top_n: int = 5) -> dict:
    top_n = max(1, min(20, int(top_n)))
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            s.client_id,
            COALESCE(c.prenom, '') AS prenom,
            COALESCE(c.nom, '') AS nom,
            COUNT(*)::int AS nb_sinistres,
            COALESCE(SUM(s.cout_sinistre_tnd), 0)::numeric AS cout_total_tnd,
            COALESCE(SUM(CASE WHEN COALESCE(CAST(s.suspicion_fraude AS INTEGER), 0) = 1 THEN 1 ELSE 0 END), 0)::int AS nb_fraude
        FROM sinistres s
        LEFT JOIN clients c ON c.client_id = s.client_id
        WHERE (%s IS NULL OR s.departement = %s)
        GROUP BY s.client_id, c.prenom, c.nom
        HAVING COUNT(*) > 0
        ORDER BY nb_sinistres DESC, cout_total_tnd DESC
        LIMIT %s
        """,
        [departement, departement, top_n],
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    payload = []
    total_claims = sum(int(r[3] or 0) for r in rows) if rows else 0
    for r in rows:
        client_id, prenom, nom, nb_sin, cout_total, nb_fraude = r
        client_name = f"{prenom} {nom}".strip() or str(client_id)
        payload.append(
            {
                "client_id": str(client_id),
                "client_name": client_name,
                "nb_sinistres": int(nb_sin or 0),
                "cout_total_tnd": float(cout_total or 0),
                "nb_fraude": int(nb_fraude or 0),
                "part_sinistres_pct": round((int(nb_sin or 0) / total_claims * 100), 1) if total_claims else 0.0,
            }
        )

    return {
        "departement": departement or "Tous",
        "top_n": top_n,
        "total_claims_top": total_claims,
        "rows": payload,
    }


# ══════════════════════════════════════════════════
# OUTIL 1 — KPI SQL
# ══════════════════════════════════════════════════
@tool
def kpi_tool(question: str) -> str:
    """
    Interroge la base PostgreSQL pour répondre à des questions sur les KPIs
    d'InsureDecide. Retourne les données chiffrées en langage naturel.
    Utilise cet outil pour : chiffres précis, comparaisons entre périodes,
    classements, totaux, moyennes.
    """
    try:
        denodo_rows = _denodo_kpi_rows()
        if denodo_rows:
            # Dernière période
            latest = max(denodo_rows, key=lambda r: (int(r.get("annee", 0)), int(r.get("mois", 0))))
            y, m = int(latest.get("annee", 0)), int(latest.get("mois", 0))
            last_period = [r for r in denodo_rows if int(r.get("annee", 0)) == y and int(r.get("mois", 0)) == m]

            context = "=== DONNÉES KPIS INSUREDECIDE — DERNIÈRE PÉRIODE (DENODO) ===\n\n"
            for r in sorted(last_period, key=lambda x: x.get("departement", "")):
                dept = r.get("departement", "Inconnu")
                periode = r.get("periode", "")
                contrats = int(r.get("nb_contrats_actifs", r.get("nb_contrats", 0)) or 0)
                primes = float(r.get("primes_acquises_tnd", 0) or 0)
                cout_sin = float(r.get("cout_sinistres_tnd", 0) or 0)
                nb_sin = int(r.get("nb_sinistres", 0) or 0)
                ratio = float(r.get("ratio_combine_pct", 0) or 0)
                resil = float(r.get("taux_resiliation_pct", 0) or 0)
                provision = float(r.get("provision_totale_tnd", 0) or 0)
                fraudes = int(r.get("nb_suspicions_fraude", 0) or 0)
                cout_moy = (cout_sin / nb_sin) if nb_sin > 0 else float(r.get("cout_moyen_sinistre_tnd", 0) or 0)

                context += (
                    f"DÉPARTEMENT {dept} — {periode}\n"
                    f"  Contrats actifs      : {contrats:,}\n"
                    f"  Primes acquises      : {primes:,.0f} TND\n"
                    f"  Coût sinistres       : {cout_sin:,.0f} TND\n"
                    f"  Nombre sinistres     : {int(nb_sin)}\n"
                    f"  Coût moyen sinistre  : {cout_moy:,.0f} TND\n"
                    f"  Ratio combiné        : {ratio:.1f}%\n"
                    f"  Taux résiliation     : {resil:.1f}%\n"
                    f"  Provisions           : {provision:,.0f} TND\n"
                    f"  Suspicions fraude    : {int(fraudes)}\n\n"
                )

            evolution = sorted(denodo_rows, key=lambda r: (int(r.get("annee", 0)), int(r.get("mois", 0))), reverse=True)[:12]
            context += "=== ÉVOLUTION RÉCENTE (12 DERNIERS MOIS) ===\n"
            for r in evolution:
                dept = r.get("departement", "Inconnu")
                periode = r.get("periode", "")
                ratio = float(r.get("ratio_combine_pct", 0) or 0)
                primes = float(r.get("primes_acquises_tnd", 0) or 0)
                resil = float(r.get("taux_resiliation_pct", 0) or 0)
                context += f"  {dept} {periode} → RC:{ratio:.1f}% | Primes:{primes:,.0f} | Résil:{resil:.1f}%\n"
            return context

        conn = get_pg()
        cur  = conn.cursor()

        # Données dernière période disponible
        cur.execute("""
            SELECT departement, periode, annee, mois,
                   nb_contrats_actifs, primes_acquises_tnd,
                   cout_sinistres_tnd, nb_sinistres,
                   ratio_combine_pct, taux_resiliation_pct,
                   provision_totale_tnd, nb_suspicions_fraude,
                   cout_moyen_sinistre_tnd
            FROM kpis_mensuels
            WHERE (annee, mois) = (
                SELECT annee, mois FROM kpis_mensuels
                ORDER BY annee DESC, mois DESC LIMIT 1
            )
            ORDER BY departement
        """)
        rows = cur.fetchall()

        # Données évolution sur 12 derniers mois
        cur.execute("""
            SELECT departement, periode, ratio_combine_pct,
                   primes_acquises_tnd, cout_sinistres_tnd, taux_resiliation_pct
            FROM kpis_mensuels
            ORDER BY annee DESC, mois DESC
            LIMIT 36
        """)
        evolution = cur.fetchall()
        cur.close(); conn.close()

        # Formatter les données pour le LLM
        context = "=== DONNÉES KPIS INSUREDECIDE — DERNIÈRE PÉRIODE ===\n\n"
        for r in rows:
            (dept, periode, annee, mois, contrats, primes, cout_sin, nb_sin,
             ratio, resil, provision, fraudes, cout_moy) = r
            context += (
                f"DÉPARTEMENT {dept} — {periode}\n"
                f"  Contrats actifs      : {contrats:,}\n"
                f"  Primes acquises      : {primes:,.0f} TND\n"
                f"  Coût sinistres       : {cout_sin:,.0f} TND\n"
                f"  Nombre sinistres     : {int(nb_sin)}\n"
                f"  Coût moyen sinistre  : {cout_moy:,.0f} TND\n"
                f"  Ratio combiné        : {ratio:.1f}%\n"
                f"  Taux résiliation     : {resil:.1f}%\n"
                f"  Provisions           : {provision:,.0f} TND\n"
                f"  Suspicions fraude    : {int(fraudes) if fraudes else 0}\n\n"
            )

        context += "=== ÉVOLUTION RÉCENTE (12 DERNIERS MOIS) ===\n"
        for r in evolution[:12]:
            dept, periode, ratio, primes, cout, resil = r
            context += f"  {dept} {periode} → RC:{ratio:.1f}% | Primes:{primes:,.0f} | Résil:{resil:.1f}%\n"

        return context

    except Exception as e:
        logger.error(f"kpi_tool error: {e}")
        return f"Erreur lors de la récupération des KPIs : {str(e)}"


# ══════════════════════════════════════════════════
# OUTIL 2 — RAG Qdrant
# ══════════════════════════════════════════════════
@tool
def rag_tool(query: str) -> str:
    """
    Recherche sémantique dans la base de connaissances d'InsureDecide.
    Contient : règles métier assurance, historique KPIs, alertes passées.
    Utilise cet outil pour : explications, contexte, règles, recommandations,
    tendances historiques, définitions métier.
    """
    try:
        client   = get_qdrant()
        embedder = get_embedder()

        query_vector = list(embedder.embed([query]))[0].tolist()

        results = []
        for collection in ["regles_metier", "kpis_mensuels", "alertes_history"]:
            hits = client.search(
                collection_name=collection,
                query_vector=query_vector,
                limit=3,
                score_threshold=0.35,
            )
            for hit in hits:
                results.append({
                    "score":      hit.score,
                    "collection": collection,
                    "text":       hit.payload.get("text", ""),
                    "meta":       {k: v for k, v in hit.payload.items() if k != "text"},
                })

        # Trier par score et garder les 6 meilleurs
        results.sort(key=lambda x: x["score"], reverse=True)
        top = results[:6]

        if not top:
            return "Aucune information pertinente trouvée dans la base de connaissances."

        context = "=== RÉSULTATS DE LA BASE DE CONNAISSANCES ===\n\n"
        for i, r in enumerate(top, 1):
            context += f"[{i}] Source: {r['collection']} (pertinence: {r['score']:.2f})\n"
            context += f"{r['text']}\n\n"

        return context

    except Exception as e:
        logger.error(f"rag_tool error: {e}")
        return f"Erreur lors de la recherche RAG : {str(e)}"


# ══════════════════════════════════════════════════
# OUTIL 3 — Alertes actives
# ══════════════════════════════════════════════════
@tool
def alerte_tool(nb_mois: int = 3) -> str:
    """
    Retourne les alertes et anomalies détectées sur les derniers mois.
    Utilise cet outil pour : questions sur les risques actuels, anomalies,
    situations critiques, recommandations d'actions urgentes.
    """
    try:
        denodo_rows = _denodo_kpi_rows()
        if denodo_rows:
            rows = sorted(denodo_rows, key=lambda r: (int(r.get("annee", 0)), int(r.get("mois", 0))))
            months = sorted({(int(r.get("annee", 0)), int(r.get("mois", 0))) for r in rows})
            keep = set(months[-(nb_mois + 1):]) if months else set()
            rows = [r for r in rows if (int(r.get("annee", 0)), int(r.get("mois", 0))) in keep]

            alertes = []
            for r in rows:
                dept = r.get("departement", "Inconnu")
                periode = r.get("periode", "")
                ratio = float(r.get("ratio_combine_pct", 0) or 0)
                resil = float(r.get("taux_resiliation_pct", 0) or 0)
                fraudes = int(r.get("nb_suspicions_fraude", 0) or 0)
                if ratio > 110:
                    alertes.append(f"🔴 CRITIQUE — {dept} {periode} : ratio combiné {ratio:.1f}% (seuil 110%)")
                elif ratio > 95:
                    alertes.append(f"🟡 WARNING  — {dept} {periode} : ratio combiné {ratio:.1f}% (seuil 95%)")
                if resil > 15:
                    alertes.append(f"🔴 CRITIQUE — {dept} {periode} : résiliation {resil:.1f}% (seuil 15%)")
                if fraudes >= 5:
                    alertes.append(f"🟡 WARNING  — {dept} {periode} : {int(fraudes)} suspicions fraude (seuil 5)")

            if not alertes:
                return "✅ Aucune anomalie détectée sur les derniers mois. Tous les indicateurs sont dans les seuils normaux."

            context = f"=== ALERTES ACTIVES — {nb_mois} DERNIERS MOIS (DENODO) ===\n\n"
            context += "\n".join(alertes)
            context += f"\n\nTotal : {len(alertes)} alerte(s) détectée(s)."
            return context

        conn = get_pg()
        cur  = conn.cursor()

        cur.execute("""
            SELECT departement, periode, annee, mois,
                   ratio_combine_pct, taux_resiliation_pct, nb_suspicions_fraude
            FROM kpis_mensuels
            WHERE (annee * 12 + mois) >= (
                SELECT MAX(annee * 12 + mois) - %s FROM kpis_mensuels
            )
            ORDER BY annee DESC, mois DESC
        """, (nb_mois,))
        rows = cur.fetchall()
        cur.close(); conn.close()

        alertes = []
        for r in rows:
            dept, periode, annee, mois, ratio, resil, fraudes = r
            if ratio > 110:
                alertes.append(f"🔴 CRITIQUE — {dept} {periode} : ratio combiné {ratio:.1f}% (seuil 110%)")
            elif ratio > 95:
                alertes.append(f"🟡 WARNING  — {dept} {periode} : ratio combiné {ratio:.1f}% (seuil 95%)")
            if resil > 15:
                alertes.append(f"🔴 CRITIQUE — {dept} {periode} : résiliation {resil:.1f}% (seuil 15%)")
            if fraudes and fraudes >= 5:
                alertes.append(f"🟡 WARNING  — {dept} {periode} : {int(fraudes)} suspicions fraude (seuil 5)")

        if not alertes:
            return "✅ Aucune anomalie détectée sur les derniers mois. Tous les indicateurs sont dans les seuils normaux."

        context = f"=== ALERTES ACTIVES — {nb_mois} DERNIERS MOIS ===\n\n"
        context += "\n".join(alertes)
        context += f"\n\nTotal : {len(alertes)} alerte(s) détectée(s)."
        return context

    except Exception as e:
        logger.error(f"alerte_tool error: {e}")
        return f"Erreur lors de la récupération des alertes : {str(e)}"


@tool
def forecast_tool(question: str) -> str:
    """
    Agent spécialisé prévision (forecasting).
    Utilise les services ML pour projeter les KPIs futurs.
    """
    try:
        from app.ml.prophet_service import get_forecast

        dept = _detect_departement(question) or "Automobile"
        ind = _detect_forecast_indicateur(question)
        nb_mois = _detect_horizon_mois(question, default=6)

        result = get_forecast(dept, ind, nb_mois)
        if result.get("error"):
            return f"Erreur prévision: {result['error']}"

        previsions = result.get("previsions", [])
        if not previsions:
            return "Aucune prévision disponible."

        lines = [
            f"=== PRÉVISION KPI ({dept}) ===",
            f"Indicateur: {ind}",
            f"Méthode: {result.get('methode', 'N/A')}",
            f"Tendance: {result.get('tendance', 'N/A')} ({result.get('variation_pct', 0)}%)",
            f"Dernière valeur réelle: {result.get('derniere_valeur', 0)}",
            f"Prochaine valeur prévue: {result.get('prochaine_valeur', 0)}",
            "",
            "Top prévisions:",
        ]
        for p in previsions[: min(6, len(previsions))]:
            lines.append(
                f"- {p.get('periode')}: {p.get('valeur')} "
                f"(intervalle {p.get('valeur_min')} à {p.get('valeur_max')})"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"forecast_tool error: {e}")
        return f"Erreur forecasting: {str(e)}"


@tool
def anomaly_tool(question: str) -> str:
    """
    Agent spécialisé détection d'anomalies (Isolation Forest).
    """
    try:
        from app.ml.anomaly_service import detect_anomalies

        dept = _detect_departement(question)
        contamination = 0.1
        q = (question or "").lower()
        if "strict" in q or "faible" in q:
            contamination = 0.05
        elif "agress" in q or "élev" in q or "eleve" in q:
            contamination = 0.15

        result = detect_anomalies(dept, contamination)
        if result.get("error"):
            return f"Erreur anomalies: {result['error']}"

        anomalies = result.get("anomalies", [])
        lines = [
            "=== DÉTECTION D'ANOMALIES ===",
            f"Département: {result.get('departement')}",
            f"Anomalies détectées: {result.get('nb_anomalies', 0)}",
            f"Contamination: {result.get('contamination', contamination)}",
            "",
        ]
        for a in anomalies[:5]:
            lines.append(
                f"- {a.get('departement')} {a.get('periode')} | "
                f"risk_score={a.get('risk_score')} | "
                f"ratio={a.get('ratio_combine_pct')} | "
                f"résiliation={a.get('taux_resiliation_pct')}"
            )
        if not anomalies:
            lines.append("Aucune anomalie majeure détectée.")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"anomaly_tool error: {e}")
        return f"Erreur anomaly detection: {str(e)}"


@tool
def drift_tool(question: str) -> str:
    """
    Agent spécialisé data drift.
    """
    try:
        from app.ml.drift_service import detect_drift

        dept = _detect_departement(question)
        result = detect_drift(dept, nb_mois_reference=12, nb_mois_courant=6)
        if result.get("error"):
            return f"Erreur drift: {result['error']}"

        lines = [
            "=== ANALYSE DATA DRIFT ===",
            f"Département: {result.get('departement')}",
            f"Niveau: {result.get('niveau')}",
            f"Drift dataset: {result.get('dataset_drift')}",
            f"Features en drift: {result.get('nb_features_drift')}/{result.get('nb_features_total')}",
            f"Message: {result.get('message')}",
            "",
            "Top features drift:",
        ]
        drift_features = [f for f in result.get("features", []) if f.get("drift_detecte")]
        for f in drift_features[:5]:
            lines.append(f"- {f.get('feature')} (p={f.get('p_value')}, stat={f.get('statistic')})")
        if not drift_features:
            lines.append("- Aucun drift significatif détecté.")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"drift_tool error: {e}")
        return f"Erreur drift detection: {str(e)}"


@tool
def explain_tool(question: str) -> str:
    """
    Agent spécialisé explicabilité (SHAP local + importance globale).
    """
    try:
        from app.ml.shap_service import explain_prediction, get_global_importance

        dept = _detect_departement(question) or "Automobile"
        dept_code = 0.0 if dept == "Automobile" else 1.0 if dept == "Vie" else 2.0
        model = "fraude" if "fraude" in (question or "").lower() else "resiliation"

        input_values = {
            "ratio_combine_pct": 105.0,
            "primes_acquises_tnd": 1500000.0,
            "cout_sinistres_tnd": 900000.0,
            "nb_sinistres": 150.0,
            "provision_totale_tnd": 300000.0,
            "nb_suspicions_fraude": 3.0,
            "dept_code": dept_code,
            "mois": 12.0,
            "annee": 2024.0,
        }

        local = explain_prediction(model, input_values)
        if local.get("status") == "error":
            return f"Erreur explainability: {local.get('detail')}"

        global_imp = get_global_importance(model)
        if global_imp.get("status") == "error":
            return f"Erreur importance globale: {global_imp.get('detail')}"

        top_local = local.get("top_factors", [])[:3]
        top_global = global_imp.get("feature_importance", [])[:5]

        lines = [
            "=== EXPLICABILITÉ MODÈLE ===",
            f"Modèle: {model}",
            f"Département simulé: {dept}",
            f"Prédiction: {local.get('prediction')} (probabilité={local.get('probability')})",
            "",
            "Facteurs locaux (SHAP):",
        ]
        for f in top_local:
            lines.append(f"- {f.get('feature')}: contribution={f.get('shap_value')} valeur={f.get('value')}")

        lines.append("")
        lines.append("Importance globale:")
        for f in top_global:
            lines.append(f"- {f.get('feature')}: {f.get('importance')}")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"explain_tool error: {e}")
        return f"Erreur explainability: {str(e)}"


@tool
def segmentation_tool(question: str) -> str:
    """
    Agent spécialisé segmentation clients (K-Means).
    """
    try:
        from app.ml.segmentation_service import get_client_segmentation

        n_clusters = _detect_n_clusters(question, default=4)
        dept = _detect_departement(question)
        result = get_client_segmentation(n_clusters=n_clusters, limit_clients=20000, departement=dept)
        if result.get("status") == "error":
            return f"Erreur segmentation: {result.get('detail')}"

        lines = [
            "=== SEGMENTATION CLIENTS ===",
            f"Algorithme: {result.get('algorithm')}",
            f"Département: {result.get('departement')}",
            f"Nombre de clusters: {result.get('n_clusters')}",
            f"Nombre de clients analysés: {result.get('nb_clients')}",
            f"Silhouette score: {result.get('silhouette_score')}",
            "",
            "Profils de segments:",
        ]
        for c in result.get("clusters", [])[:8]:
            lines.append(
                f"- Cluster {c.get('cluster')} ({c.get('segment_label')}): "
                f"clients={c.get('nb_clients')}, prime_moy={c.get('avg_prime_annuelle_tnd')}, "
                f"fraude_rate={c.get('avg_fraude_rate')}, resiliation_rate={c.get('avg_resiliation_rate')}"
            )

        lines.append("")
        lines.append("Top clients (aperçu):")
        for t in result.get("top_clients", [])[:5]:
            lines.append(
                f"- {t.get('client_id')} | {t.get('segment_label')} | "
                f"prime={t.get('total_prime_annuelle_tnd')} | contrats={t.get('nb_contrats')}"
            )

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"segmentation_tool error: {e}")
        return f"Erreur segmentation: {str(e)}"


@tool
def client_tool(question: str) -> str:
    """
    Agent spécialisé clients: top clients par sinistres avec identifiants/noms réels.
    """
    try:
        if is_specific_client_question(question):
            profile = get_client_claims_profile(question)
            status = profile.get("status")

            if status == "ambiguous":
                candidates = profile.get("candidates", [])[:5]
                breakdown_map = _get_clients_dept_breakdown([c.get("client_id") for c in candidates])
                lines = [
                    "=== FICHE CLIENT — HOMONYMES ===",
                    "Plusieurs clients portent le même nom.",
                    "",
                    "Tableau standardise:",
                    "",
                    "ID Client ; Nom Complet ; Total Sinistres ; Repartition Departements",
                ]
                for c in candidates:
                    dep_rows = breakdown_map.get(c.get("client_id"), [])
                    dep_text = "-"
                    if dep_rows:
                        dep_text = ", ".join(
                            f"{d.get('departement')}:{d.get('nb_sinistres')}"
                            for d in dep_rows
                        )
                    lines.append(
                        f"{c.get('client_id')} ; {c.get('client_name')} ; {c.get('nb_sinistres', '-')} ; {dep_text}"
                    )
                lines.append("")
                lines.append("Action requise: préciser le client_id (ex: CLTxxxxxx).")
                return "\n".join(lines)

            if status != "ok":
                return f"Impossible de retrouver le client demandé. Détail: {profile.get('reason', 'non disponible')}"

            dep_rows = profile.get("departements", [])
            if not dep_rows:
                return (
                    f"Client {profile.get('client_id')} ({profile.get('client_name')}) retrouvé, "
                    "mais aucun sinistre associé dans la base."
                )

            lines = [
                "=== FICHE CLIENT ===",
                f"ID Client: {profile.get('client_id')}",
                f"Nom Client: {profile.get('client_name')}",
                f"Total Sinistres: {profile.get('nb_sinistres_total')}",
                "",
                "Tableau standardise:",
                "",
                "Departement ; Nb Sinistres ; Part (%) ; Cout Total (TND)",
            ]
            for d in dep_rows:
                lines.append(
                    f"{d.get('departement')} ; {d.get('nb_sinistres')} ; {d.get('part_pct')} ; {d.get('cout_total_tnd')}"
                )

            lines.append("")
            lines.append("Derniers sinistres (aperçu):")
            for s in profile.get("sinistres", [])[:5]:
                lines.append(
                    f"- {s.get('sinistre_id')} | {s.get('departement')} | {s.get('date_sinistre')} | "
                    f"{s.get('type_sinistre')} | coût={s.get('cout_tnd')} | statut={s.get('statut')}"
                )
            return "\n".join(lines)

        dept = _detect_departement(question)
        top_n = _detect_top_n(question, default=5)
        result = get_top_clients_claims(departement=dept, top_n=top_n)
        rows = result.get("rows", [])
        if not rows:
            return "Aucune donnée client/sinistre disponible pour la requête."

        lines = [
            "=== FICHE CLIENTS — TOP SINISTRES ===",
            f"Departement: {result.get('departement')}",
            f"Top Demande: {result.get('top_n')}",
            f"Total Sinistres Top: {result.get('total_claims_top')}",
            "",
            "Tableau standardise:",
            "",
            "ID Client ; Nom Client ; Nb Sinistres ; Part Sinistres (%) ; Cout Total (TND)",
        ]

        for r in rows:
            lines.append(
                f"{r.get('client_id')} ; {r.get('client_name')} ; {r.get('nb_sinistres')} ; "
                f"{r.get('part_sinistres_pct')} ; {r.get('cout_total_tnd')}"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"client_tool error: {e}")
        return f"Erreur client analytics: {str(e)}"


@tool
def sql_tool(question: str) -> str:
    """
    Agent NLP -> SQL déterministe pour analytics opérationnelles sur PostgreSQL.
    """
    try:
        result = run_sql_analytics(question)
        status = result.get("status")

        if status == "unsupported":
            return "Intent SQL non supporté pour cette question."

        if status == "empty":
            return "Aucune donnée trouvée pour les filtres demandés."

        rows = result.get("rows", [])
        top = result.get("top") or {}
        scope = result.get("scope") or {}
        qtype = result.get("query_type")

        if qtype == "total_clients":
            total = int((top or {}).get("value") or 0)
            lines = [
                "=== FICHE ANALYSE CLIENTS ===",
                f"Type Requete: {qtype}",
                f"Departement: {scope.get('departement', 'Tous')}",
                "",
                f"Reponse: Nombre total de clients = {total}.",
                "",
                "Tableau standardise:",
                "",
                "Metrique ; Valeur",
                f"Total Clients ; {total}",
            ]
            return "\n".join(lines)

        lines = [
            "=== FICHE ANALYSE SINISTRES ===",
            f"Type Requete: {qtype}",
            f"Departement: {scope.get('departement', 'Tous')}",
            f"Periode: {scope.get('year') or 'Toutes'}{('-' + str(scope.get('month')).zfill(2)) if scope.get('month') else ''}",
            f"Top N: {scope.get('top_n')}",
            "",
            f"Gouvernorat Top 1: {top.get('gouvernorat')} ({top.get('nb_sinistres')} sinistres)",
            "",
            "Tableau standardise:",
            "",
            "Gouvernorat ; Nb Sinistres ; Part (%) ; Cout Total (TND)",
        ]
        for r in rows:
            lines.append(
                f"{r.get('gouvernorat')} ; {r.get('nb_sinistres')} ; {r.get('part_pct')} ; {r.get('cout_total_tnd')}"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"sql_tool error: {e}")
        return f"Erreur SQL analytics: {str(e)}"


@tool
def data_query_tool(question: str) -> str:
    """
    Facade unifiée des requêtes data.
    - Route vers SQL déterministe pour les questions analytiques ad-hoc.
    - Fallback vers contexte KPI standard pour les questions de pilotage.
    """
    sql_result = run_sql_analytics(question)
    if sql_result.get("status") in {"ok", "empty"}:
        return sql_tool.invoke(question)
    return kpi_tool.invoke(question)


# Liste des outils disponibles pour LangGraph
TOOLS = [
    kpi_tool,
    rag_tool,
    alerte_tool,
    forecast_tool,
    anomaly_tool,
    drift_tool,
    explain_tool,
    segmentation_tool,
    client_tool,
    sql_tool,
    data_query_tool,
]
