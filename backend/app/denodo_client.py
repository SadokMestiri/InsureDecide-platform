"""
InsureDecide — Client Denodo Platform 9.0
Fix : URL $format=json directement (pas via params)
Fix : colonnes correctes (client_id, sinistre_id, contrat_id)
"""

import os
import logging
import requests
import psycopg2
from requests.auth import HTTPBasicAuth
from urllib.parse import quote
from decimal import Decimal

logger = logging.getLogger(__name__)

DENODO_URL      = os.getenv("DENODO_URL",      "http://172.16.60.6:9090")
DENODO_USER     = os.getenv("DENODO_USER",     "admin")
DENODO_PASSWORD = os.getenv("DENODO_PASSWORD", "admin")
DENODO_DB       = os.getenv("DENODO_DB",       "insuredecide")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://insuredecide_user:insuredecide_pass@postgres:5432/insuredecide"
)

DENODO_BASE = f"{DENODO_URL}/denodo-restfulws/{DENODO_DB}/views"
AUTH        = HTTPBasicAuth(DENODO_USER, DENODO_PASSWORD)
TIMEOUT     = 8


def is_denodo_available() -> bool:
    try:
        url = f"{DENODO_BASE}/vue_kpis_enrichis?$format=json"
        r = requests.get(url, auth=AUTH, timeout=TIMEOUT,
                         headers={"Accept": "application/json"})
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"[Denodo] Indisponible : {e}")
        return False


def query_denodo(view: str, filter_expr: str = None) -> dict:
    url = f"{DENODO_BASE}/{view}?$format=json"
    if filter_expr:
        url += f"&$filter={quote(filter_expr)}"
    r = requests.get(url, auth=AUTH, timeout=10,
                     headers={"Accept": "application/json"})
    r.raise_for_status()
    data = r.json()
    elements = data.get("elements") or data.get("value") or []
    return {"data": elements, "count": len(elements), "source": "denodo"}


def query_denodo_filter(view: str, filter_expr: str) -> dict:
    return query_denodo(view, filter_expr)


def get_kpis_enrichis(departement: str = None) -> dict:
    if is_denodo_available():
        try:
            f = f"departement eq '{departement}'" if departement else None
            return query_denodo("vue_kpis_enrichis", f)
        except Exception as e:
            logger.warning(f"[Denodo] Erreur vue_kpis_enrichis : {e}, fallback PostgreSQL")
    return _pg_kpis_enrichis(departement)


def get_client_360(client_id: int) -> dict:
    if is_denodo_available():
        try:
            result = query_denodo("vue_client_360", f"client_id eq '{client_id}'")
            if result["data"]:
                return {"data": result["data"][0], "source": "denodo"}
        except Exception as e:
            logger.warning(f"[Denodo] Erreur vue_client_360 : {e}, fallback PostgreSQL")
    return _pg_client_360(client_id)


def get_sinistres_enrichis(gouvernorat: str = None, limit: int = 100) -> dict:
    if is_denodo_available():
        try:
            f = f"gouvernorat eq '{gouvernorat}'" if gouvernorat else None
            return query_denodo("vue_sinistres_enrichis", f)
        except Exception as e:
            logger.warning(f"[Denodo] Erreur vue_sinistres_enrichis : {e}, fallback PostgreSQL")
    return _pg_sinistres_enrichis(gouvernorat, limit)


def get_geo_resume() -> dict:
    if is_denodo_available():
        try:
            return query_denodo("vue_geo_resume")
        except Exception as e:
            logger.warning(f"[Denodo] Erreur vue_geo_resume : {e}, fallback PostgreSQL")
    return _pg_geo_resume()


def get_contrats_unifies(client_id: int = None) -> dict:
    if is_denodo_available():
        try:
            f = f"client_id eq '{client_id}'" if client_id else None
            return query_denodo("vue_contrats_unifies", f)
        except Exception as e:
            logger.warning(f"[Denodo] Erreur vue_contrats_unifies : {e}, fallback PostgreSQL")
    return _pg_contrats_unifies(client_id)


def _pg_conn():
    return psycopg2.connect(DATABASE_URL)


def _clean(val):
    if isinstance(val, Decimal): return float(val)
    if val is None: return None
    return val


def _pg_kpis_enrichis(departement: str = None) -> dict:
    conn = _pg_conn()
    cur  = conn.cursor()
    q = """
        SELECT annee, mois, departement,
               ratio_combine_pct, primes_acquises_tnd, cout_sinistres_tnd,
               nb_sinistres, taux_resiliation_pct, provision_totale_tnd,
               nb_suspicions_fraude,
               CASE
                 WHEN ratio_combine_pct > 110 THEN 'critique'
                 WHEN ratio_combine_pct > 95  THEN 'attention'
                 ELSE 'normal'
               END AS alerte_ratio,
               cout_sinistres_tnd / NULLIF(primes_acquises_tnd, 0) AS loss_ratio_calc
        FROM kpis_mensuels
    """
    params = []
    if departement:
        q += " WHERE departement = %s"
        params.append(departement)
    q += " ORDER BY annee DESC, mois DESC LIMIT 100"
    cur.execute(q, params)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, [_clean(v) for v in row])) for row in cur.fetchall()]
    cur.close(); conn.close()
    return {"data": rows, "count": len(rows), "source": "postgresql_direct"}


def _pg_client_360(client_id: int) -> dict:
    conn = _pg_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT c.client_id, c.nom, c.prenom, c.gouvernorat, c.age,
               COUNT(DISTINCT ca.contrat_id) AS nb_contrats_auto,
               COUNT(DISTINCT cv.contrat_id) AS nb_contrats_vie,
               COUNT(DISTINCT ci.contrat_id) AS nb_contrats_immo,
               COUNT(DISTINCT s.sinistre_id) AS nb_sinistres
        FROM clients c
        LEFT JOIN contrats_automobile ca ON c.client_id = ca.client_id
        LEFT JOIN contrats_vie cv         ON c.client_id = cv.client_id
        LEFT JOIN contrats_immobilier ci  ON c.client_id = ci.client_id
        LEFT JOIN sinistres s             ON c.client_id = s.client_id
        WHERE c.client_id = %s::text
        GROUP BY c.client_id, c.nom, c.prenom, c.gouvernorat, c.age
    """, [client_id])
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    cur.close(); conn.close()
    if not row:
        return {"data": None, "source": "postgresql_direct", "error": "Client non trouvé"}
    return {"data": dict(zip(cols, [_clean(v) for v in row])), "source": "postgresql_direct"}


def _pg_sinistres_enrichis(gouvernorat: str = None, limit: int = 100) -> dict:
    conn = _pg_conn()
    cur  = conn.cursor()
    q = """
        SELECT s.sinistre_id, s.date_sinistre, s.cout_sinistre_tnd,
               s.gouvernorat, s.type_sinistre,
               c.nom, c.prenom, c.age
        FROM sinistres s
        JOIN clients c ON s.client_id = c.client_id
    """
    params = []
    if gouvernorat:
        q += " WHERE s.gouvernorat = %s"
        params.append(gouvernorat)
    q += f" ORDER BY s.date_sinistre DESC LIMIT {limit}"
    cur.execute(q, params)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, [_clean(v) for v in row])) for row in cur.fetchall()]
    cur.close(); conn.close()
    return {"data": rows, "count": len(rows), "source": "postgresql_direct"}


def _pg_geo_resume() -> dict:
    conn = _pg_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT gouvernorat,
               COUNT(*)               AS nb_sinistres,
               SUM(cout_sinistre_tnd) AS cout_total_tnd,
               AVG(cout_sinistre_tnd) AS cout_moyen_tnd
        FROM sinistres
        GROUP BY gouvernorat
        ORDER BY nb_sinistres DESC
    """)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, [_clean(v) for v in row])) for row in cur.fetchall()]
    cur.close(); conn.close()
    return {"data": rows, "count": len(rows), "source": "postgresql_direct"}


def _pg_contrats_unifies(client_id: int = None) -> dict:
    conn = _pg_conn()
    cur  = conn.cursor()
    where = f"WHERE client_id = '{client_id}'" if client_id else ""
    q = f"""
        SELECT contrat_id, client_id, 'Automobile' AS departement,
               date_debut, date_fin, prime_annuelle_tnd, statut
        FROM contrats_automobile {where}
        UNION ALL
        SELECT contrat_id, client_id, 'Vie',
               date_debut, date_fin, prime_annuelle_tnd, statut
        FROM contrats_vie {where}
        UNION ALL
        SELECT contrat_id, client_id, 'Immobilier',
               date_debut, date_fin, prime_annuelle_tnd, statut
        FROM contrats_immobilier {where}
        ORDER BY departement LIMIT 500
    """
    cur.execute(q)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, [_clean(v) for v in row])) for row in cur.fetchall()]
    cur.close(); conn.close()
    return {"data": rows, "count": len(rows), "source": "postgresql_direct"}