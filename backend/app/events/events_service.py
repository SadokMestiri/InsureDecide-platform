"""
InsureDecide — Service Événements Métier
Détecte et génère automatiquement les événements importants depuis PostgreSQL.
Stocke dans MongoDB pour le fil d'événements (feed).
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import psycopg2
from decimal import Decimal
from pymongo import MongoClient, DESCENDING
from pymongo.errors import ServerSelectionTimeoutError

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL",  "postgresql://insuredecide_user:insuredecide_pass@postgres:5432/insuredecide")
MONGODB_URL  = os.getenv("MONGODB_URL",   "mongodb://insuredecide_user:insuredecide_pass@mongodb:27017/insuredecide?authSource=admin")

# Types d'événements
EVENT_TYPES = {
    "ratio_critique":   { "icon": "🔴", "category": "risque",      "color": "#ef4444" },
    "ratio_warning":    { "icon": "🟡", "category": "surveillance", "color": "#f59e0b" },
    "resiliation_haute":{ "icon": "🔴", "category": "risque",      "color": "#ef4444" },
    "fraude_detectee":  { "icon": "🟡", "category": "fraude",      "color": "#f59e0b" },
    "bonne_performance":{ "icon": "🟢", "category": "positif",     "color": "#10b981" },
    "tendance_hausse":  { "icon": "📈", "category": "tendance",    "color": "#f59e0b" },
    "tendance_baisse":  { "icon": "📉", "category": "tendance",    "color": "#10b981" },
    "nouveau_mois":     { "icon": "📅", "category": "info",        "color": "#2563eb" },
}


def clean(obj):
    """Convertit les types PostgreSQL non-sérialisables en types Python natifs."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(i) for i in obj]
    return obj


def get_pg():
    return psycopg2.connect(DATABASE_URL)


def get_mongo():
    try:
        # Forcer les paramètres d'auth explicitement (contourne bug pymongo + authSource URL)
        client = MongoClient(
            host="mongodb",
            port=27017,
            username="insuredecide_user",
            password="insuredecide_pass",
            authSource="admin",
            serverSelectionTimeoutMS=3000,
        )
        client.admin.command("ping")
        return client["insuredecide"]
    except Exception as e:
        logger.warning(f"⚠️ MongoDB non disponible : {e}")
        return None


def detect_events_from_kpis() -> List[Dict[str, Any]]:
    """
    Analyse les KPIs et génère des événements métier automatiquement.
    Compare le dernier mois avec le mois précédent pour détecter les tendances.
    """
    conn = get_pg()
    cur  = conn.cursor()

    # Dernière période et période précédente
    cur.execute("""
        SELECT k.departement, k.periode, k.annee, k.mois,
               k.ratio_combine_pct, k.taux_resiliation_pct,
               k.nb_suspicions_fraude, k.primes_acquises_tnd,
               k.cout_sinistres_tnd, k.nb_sinistres,
               prev.ratio_combine_pct as prev_ratio,
               prev.primes_acquises_tnd as prev_primes
        FROM kpis_mensuels k
        LEFT JOIN kpis_mensuels prev
            ON prev.departement = k.departement
            AND (
                (k.mois > 1  AND prev.annee = k.annee   AND prev.mois = k.mois - 1)
                OR
                (k.mois = 1  AND prev.annee = k.annee-1 AND prev.mois = 12)
            )
        WHERE (k.annee, k.mois) = (
            SELECT annee, mois FROM kpis_mensuels
            ORDER BY annee DESC, mois DESC LIMIT 1
        )
        ORDER BY k.departement
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    events = []
    now    = datetime.now(timezone.utc)

    for r in rows:
        (dept, periode, annee, mois, ratio, resil, fraudes,
         primes, cout_sin, nb_sin, prev_ratio, prev_primes) = r

        # ── Ratio combiné critique
        if ratio > 110:
            events.append({
                "type":       "ratio_critique",
                "departement": dept,
                "periode":    periode,
                "titre":      f"{dept} — Ratio combiné critique",
                "message":    f"Le ratio combiné atteint {ratio:.1f}% — le département perd {ratio-100:.1f} centimes par dinar encaissé. Action immédiate requise.",
                "valeur":     ratio,
                "seuil":      110,
                "severite":   "critique",
                "timestamp":  now,
                **EVENT_TYPES["ratio_critique"],
            })
        elif ratio > 95:
            events.append({
                "type":       "ratio_warning",
                "departement": dept,
                "periode":    periode,
                "titre":      f"{dept} — Ratio combiné en alerte",
                "message":    f"Ratio combiné à {ratio:.1f}% — seuil de rentabilité à surveiller.",
                "valeur":     ratio,
                "seuil":      95,
                "severite":   "warning",
                "timestamp":  now,
                **EVENT_TYPES["ratio_warning"],
            })
        else:
            events.append({
                "type":       "bonne_performance",
                "departement": dept,
                "periode":    periode,
                "titre":      f"{dept} — Bonne performance technique",
                "message":    f"Ratio combiné sain à {ratio:.1f}% — département rentable.",
                "valeur":     ratio,
                "seuil":      95,
                "severite":   "info",
                "timestamp":  now,
                **EVENT_TYPES["bonne_performance"],
            })

        # ── Taux de résiliation
        if resil > 15:
            events.append({
                "type":       "resiliation_haute",
                "departement": dept,
                "periode":    periode,
                "titre":      f"{dept} — Crise de rétention clients",
                "message":    f"Taux de résiliation à {resil:.1f}% — seuil critique dépassé (15%). Lancer une campagne de fidélisation.",
                "valeur":     resil,
                "seuil":      15,
                "severite":   "critique",
                "timestamp":  now,
                **EVENT_TYPES["resiliation_haute"],
            })

        # ── Fraudes
        if fraudes and fraudes >= 5:
            events.append({
                "type":       "fraude_detectee",
                "departement": dept,
                "periode":    periode,
                "titre":      f"{dept} — Suspicions de fraude",
                "message":    f"{int(fraudes)} suspicions de fraude détectées ce mois. Investigation recommandée.",
                "valeur":     int(fraudes),
                "seuil":      5,
                "severite":   "warning",
                "timestamp":  now,
                **EVENT_TYPES["fraude_detectee"],
            })

        # ── Tendances ratio vs mois précédent
        if prev_ratio is not None:
            variation = ratio - prev_ratio
            if variation > 10:
                events.append({
                    "type":       "tendance_hausse",
                    "departement": dept,
                    "periode":    periode,
                    "titre":      f"{dept} — Dégradation du ratio combiné",
                    "message":    f"Ratio combiné en hausse de +{variation:.1f}% vs mois précédent ({prev_ratio:.1f}% → {ratio:.1f}%).",
                    "valeur":     variation,
                    "seuil":      10,
                    "severite":   "warning",
                    "timestamp":  now,
                    **EVENT_TYPES["tendance_hausse"],
                })
            elif variation < -5:
                events.append({
                    "type":       "tendance_baisse",
                    "departement": dept,
                    "periode":    periode,
                    "titre":      f"{dept} — Amélioration du ratio combiné",
                    "message":    f"Ratio combiné en baisse de {variation:.1f}% vs mois précédent ({prev_ratio:.1f}% → {ratio:.1f}%). Bonne tendance.",
                    "valeur":     abs(variation),
                    "seuil":      5,
                    "severite":   "info",
                    "timestamp":  now,
                    **EVENT_TYPES["tendance_baisse"],
                })

    return events


def save_events_to_mongo(events: List[Dict]) -> int:
    """Sauvegarde les événements dans MongoDB (upsert par clé unique)."""
    db = get_mongo()
    if db is None:
        return 0

    col   = db["events"]
    saved = 0
    for ev in events:
        ev  = clean(ev)
        key = { "type": ev["type"], "departement": ev["departement"], "periode": ev["periode"] }
        col.update_one(key, {"$set": ev}, upsert=True)
        saved += 1

    # Index pour les requêtes fréquentes
    col.create_index([("timestamp", DESCENDING)])
    col.create_index([("severite",  1)])
    col.create_index([("departement", 1)])

    return saved


def get_feed(limit: int = 20, departement: Optional[str] = None,
             severite: Optional[str] = None) -> List[Dict]:
    """Récupère le fil d'événements depuis MongoDB."""
    db = get_mongo()

    if db is None:
        # Fallback : générer depuis PostgreSQL si MongoDB indisponible
        events = detect_events_from_kpis()
        if departement:
            events = [e for e in events if e["departement"] == departement]
        if severite:
            events = [e for e in events if e["severite"] == severite]
        return events[:limit]

    col    = db["events"]
    query  = {}
    if departement:
        query["departement"] = departement
    if severite:
        query["severite"] = severite

    docs = list(col.find(query, {"_id": 0}).sort("timestamp", DESCENDING).limit(limit))
    return docs


def refresh_events() -> Dict[str, int]:
    """Détecte et sauvegarde tous les événements. Retourne le compte."""
    events = detect_events_from_kpis()
    saved  = save_events_to_mongo(events)
    logger.info(f"🔄 {len(events)} événements détectés, {saved} sauvegardés MongoDB")
    return {"detected": len(events), "saved": saved}