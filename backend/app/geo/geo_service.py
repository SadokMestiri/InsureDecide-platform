"""
InsureDecide — Service Géographique
Agrège les données de sinistres, contrats et clients par gouvernorat.
"""

import os
import logging
import psycopg2
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://insuredecide_user:insuredecide_pass@postgres:5432/insuredecide")

# Coordonnées GPS des 24 gouvernorats tunisiens
GOUVERNORAT_COORDS = {
    "Tunis":          {"lat": 36.8190, "lng": 10.1658},
    "Ariana":         {"lat": 36.8625, "lng": 10.1956},
    "Ben Arous":      {"lat": 36.7533, "lng": 10.2281},
    "Manouba":        {"lat": 36.8078, "lng": 10.0963},
    "Nabeul":         {"lat": 36.4561, "lng": 10.7376},
    "Zaghouan":       {"lat": 36.4029, "lng": 10.1429},
    "Bizerte":        {"lat": 37.2744, "lng": 9.8739},
    "Béja":           {"lat": 36.7256, "lng": 9.1817},
    "Jendouba":       {"lat": 36.5011, "lng": 8.7757},
    "Kef":            {"lat": 36.1826, "lng": 8.7149},
    "Siliana":        {"lat": 36.0849, "lng": 9.3708},
    "Sousse":         {"lat": 35.8245, "lng": 10.6346},
    "Monastir":       {"lat": 35.7643, "lng": 10.8113},
    "Mahdia":         {"lat": 35.5047, "lng": 11.0622},
    "Sfax":           {"lat": 34.7406, "lng": 10.7603},
    "Kairouan":       {"lat": 35.6781, "lng": 10.0963},
    "Kasserine":      {"lat": 35.1676, "lng": 8.8365},
    "Sidi Bouzid":    {"lat": 35.0382, "lng": 9.4849},
    "Gabès":          {"lat": 33.8814, "lng": 10.0982},
    "Médenine":       {"lat": 33.3549, "lng": 10.5055},
    "Tataouine":      {"lat": 32.9211, "lng": 10.4514},
    "Gafsa":          {"lat": 34.4250, "lng": 8.7842},
    "Tozeur":         {"lat": 33.9197, "lng": 8.1336},
    "Kébili":         {"lat": 33.7042, "lng": 8.9650},
}


def _clean(val):
    if isinstance(val, Decimal):
        return float(val)
    return val


def get_sinistres_par_gouvernorat(departement: Optional[str] = None) -> list:
    """
    Agrège les sinistres par gouvernorat.
    Retourne : gouvernorat, nb_sinistres, cout_total, cout_moyen,
               nb_fraudes, nb_contrats, taux_sinistralite
    """
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    dept_filter = ""
    params = []
    if departement and departement != "tous":
        dept_filter = "WHERE s.gouvernorat IS NOT NULL AND LOWER(s.departement) = LOWER(%s)"
        params.append(departement)
    else:
        dept_filter = "WHERE s.gouvernorat IS NOT NULL"

    cur.execute(f"""
        SELECT
            s.gouvernorat,
            COUNT(*)                                    AS nb_sinistres,
            COALESCE(SUM(s.cout_sinistre_tnd), 0)         AS cout_total,
            COALESCE(AVG(s.cout_sinistre_tnd), 0)         AS cout_moyen,
            COUNT(CASE WHEN s.suspicion_fraude THEN 1 END) AS nb_fraudes,
            s.departement
        FROM sinistres s
        {dept_filter}
        GROUP BY s.gouvernorat, s.departement
        ORDER BY nb_sinistres DESC
    """, params)

    rows = cur.fetchall()

    # Agréger par gouvernorat (tous départements confondus si pas de filtre)
    gov_data = {}
    for gov, nb_sin, cout_tot, cout_moy, nb_fraudes, dept in rows:
        if gov not in gov_data:
            gov_data[gov] = {
                "gouvernorat": gov,
                "nb_sinistres": 0,
                "cout_total":   0.0,
                "nb_fraudes":   0,
                "departements": {},
                **GOUVERNORAT_COORDS.get(gov, {"lat": 34.0, "lng": 9.0}),
            }
        gov_data[gov]["nb_sinistres"] += int(nb_sin)
        gov_data[gov]["cout_total"]   += _clean(cout_tot)
        gov_data[gov]["nb_fraudes"]   += int(nb_fraudes)
        gov_data[gov]["departements"][dept] = int(nb_sin)

    # Calculer cout_moyen
    for gov in gov_data:
        nb = gov_data[gov]["nb_sinistres"]
        gov_data[gov]["cout_moyen"] = round(gov_data[gov]["cout_total"] / nb, 0) if nb > 0 else 0
        gov_data[gov]["cout_total"] = round(gov_data[gov]["cout_total"], 0)

    # Ajouter nb_contrats par gouvernorat
    cur.execute("""
        SELECT gouvernorat, COUNT(*) as nb
        FROM (
            SELECT gouvernorat FROM contrats_automobile WHERE gouvernorat IS NOT NULL
            UNION ALL
            SELECT gouvernorat FROM contrats_immobilier WHERE gouvernorat IS NOT NULL
        ) AS all_contrats(gouvernorat)
        GROUP BY gouvernorat
    """)
    for gov, nb in cur.fetchall():
        if gov in gov_data:
            gov_data[gov]["nb_contrats"] = int(nb)
            sin = gov_data[gov]["nb_sinistres"]
            gov_data[gov]["taux_sinistralite"] = round(sin / int(nb) * 100, 1) if int(nb) > 0 else 0
        
    cur.close()
    conn.close()

    result = sorted(gov_data.values(), key=lambda x: x["nb_sinistres"], reverse=True)
    return result


def get_top_gouvernorats(departement: Optional[str] = None, limit: int = 5) -> list:
    """Retourne les N gouvernorats avec le plus de sinistres."""
    data = get_sinistres_par_gouvernorat(departement)
    return data[:limit]


def get_gouvernorat_detail(gouvernorat: str) -> dict:
    """Détail complet d'un gouvernorat : sinistres, contrats, clients."""
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    # Sinistres par département
    cur.execute("""
        SELECT departement,
               COUNT(*) as nb_sinistres,
               AVG(cout_sinistre_tnd) as cout_moyen,
               COUNT(CASE WHEN suspicion_fraude THEN 1 END) as nb_fraudes
        FROM sinistres
        WHERE gouvernorat = %s
        GROUP BY departement
    """, [gouvernorat])
    sinistres_dept = [
        {"departement": r[0], "nb_sinistres": int(r[1]),
         "cout_moyen": round(_clean(r[2] or 0), 0), "nb_fraudes": int(r[3])}
        for r in cur.fetchall()
    ]

    # Nb clients
    cur.execute("SELECT COUNT(*) FROM clients WHERE gouvernorat = %s", [gouvernorat])
    nb_clients = cur.fetchone()[0]

    # Top sinistres récents
    cur.execute("""
        SELECT s.contrat_id, s.departement, s.type_sinistre,
               s.cout_sinistre_tnd, s.date_sinistre, s.suspicion_fraude
        FROM sinistres s
        WHERE s.gouvernorat = %s
        ORDER BY s.cout_sinistre_tnd DESC NULLS LAST
        LIMIT 5
    """, [gouvernorat])
    top_sinistres = [
        {"contrat_id": r[0], "departement": r[1], "type": r[2],
         "cout": round(_clean(r[3] or 0), 0),
         "date": str(r[4]) if r[4] else "", "fraude": bool(r[5])}
        for r in cur.fetchall()
    ]

    cur.close()
    conn.close()

    coords = GOUVERNORAT_COORDS.get(gouvernorat, {"lat": 34.0, "lng": 9.0})
    return {
        "gouvernorat":    gouvernorat,
        "nb_clients":     int(nb_clients),
        "sinistres_dept": sinistres_dept,
        "top_sinistres":  top_sinistres,
        **coords,
    }