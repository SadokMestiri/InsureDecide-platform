"""
InsureDecide — DAG Airflow Principal
Planification : tous les jours à 02h00

Tâches :
  1. health_check     → vérifie PostgreSQL + Qdrant + backend
  2. refresh_events   → détecte et sauvegarde les événements métier dans MongoDB
  3. reindex_qdrant   → re-vectorise les KPIs dans Qdrant pour le RAG
  4. notify_critiques → envoie les alertes critiques via le WebSocket (broadcast)
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
import requests
import logging

logger = logging.getLogger(__name__)

BACKEND_URL = "http://insuredecide_backend:8000"

default_args = {
    "owner":            "insuredecide",
    "depends_on_past":  False,
    "retries":          2,
    "retry_delay":      timedelta(minutes=3),
    "email_on_failure": False,
}


# ══════════════════════════════════════
# TÂCHE 1 — Health Check
# ══════════════════════════════════════
def task_health_check(**ctx):
    """Vérifie que le backend est opérationnel avant de lancer le pipeline."""
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=10)
        data = r.json()
        logger.info(f"Backend status: {data}")
        if data.get("status") not in ("healthy", "degraded"):
            raise Exception(f"Backend unhealthy: {data}")
        return "healthy"
    except Exception as e:
        raise Exception(f"Health check échoué: {e}")


# ══════════════════════════════════════
# TÂCHE 2 — Refresh événements MongoDB
# ══════════════════════════════════════
def task_refresh_events(**ctx):
    """Détecte les événements métier et les sauvegarde dans MongoDB."""
    r = requests.post(f"{BACKEND_URL}/api/events/refresh", timeout=30)
    r.raise_for_status()
    data = r.json()
    logger.info(f"✅ Événements : {data['detected']} détectés, {data['saved']} sauvegardés")

    # Pousser les stats dans XCom pour la tâche suivante
    ctx["ti"].xcom_push(key="events_count",    value=data["detected"])
    ctx["ti"].xcom_push(key="critiques_count", value=data.get("critiques", 0))
    return data


# ══════════════════════════════════════
# TÂCHE 3 — Réindexation Qdrant
# ══════════════════════════════════════
def task_reindex_qdrant(**ctx):
    """Re-vectorise tous les KPIs dans Qdrant pour maintenir le RAG à jour."""
    logger.info("🔄 Démarrage réindexation Qdrant...")
    r = requests.post(f"{BACKEND_URL}/api/agent/index", timeout=300)
    r.raise_for_status()
    data = r.json()
    logger.info(f"✅ Qdrant réindexé : {data}")
    return data


# ══════════════════════════════════════
# TÂCHE 4 — Récupérer les stats du feed
# ══════════════════════════════════════
def task_check_critiques(**ctx):
    """Vérifie les alertes critiques et log un résumé."""
    r = requests.get(f"{BACKEND_URL}/api/events/stats", timeout=15)
    r.raise_for_status()
    stats = r.json()

    critiques = stats.get("par_severite", {}).get("critique", 0)
    warnings  = stats.get("par_severite", {}).get("warning",  0)

    logger.info(f"📊 Résumé pipeline InsureDecide :")
    logger.info(f"   Total événements : {stats['total']}")
    logger.info(f"   Critiques        : {critiques}")
    logger.info(f"   Warnings         : {warnings}")
    logger.info(f"   Par département  : {stats.get('par_departement', {})}")

    if critiques > 0:
        logger.warning(f"⚠️  {critiques} alertes critiques actives — intervention CEO recommandée")

    return {
        "total":     stats["total"],
        "critiques": critiques,
        "warnings":  warnings,
    }


# ══════════════════════════════════════
# BRANCH — Sauter réindexation si déjà récente
# ══════════════════════════════════════
def branch_should_reindex(**ctx):
    """Réindexe Qdrant seulement le lundi (hebdomadaire) ou si forcé."""
    exec_date = ctx["execution_date"]
    # Réindexation complète chaque lundi + premier jour du mois
    if exec_date.weekday() == 0 or exec_date.day == 1:
        logger.info("🔄 Réindexation Qdrant planifiée (lundi/1er du mois)")
        return "reindex_qdrant"
    else:
        logger.info("⏭️  Réindexation Qdrant ignorée aujourd'hui")
        return "skip_reindex"


# ══════════════════════════════════════
# DÉFINITION DU DAG
# ══════════════════════════════════════
with DAG(
    dag_id="insuredecide_pipeline",
    description="Pipeline automatique InsureDecide — événements + RAG + alertes",
    default_args=default_args,
    schedule_interval="0 2 * * *",   # Tous les jours à 02h00
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["insuredecide", "production"],
) as dag:

    start = EmptyOperator(task_id="start")
    end   = EmptyOperator(task_id="end")

    health_check = PythonOperator(
        task_id="health_check",
        python_callable=task_health_check,
    )

    refresh_events = PythonOperator(
        task_id="refresh_events",
        python_callable=task_refresh_events,
    )

    branch_reindex = BranchPythonOperator(
        task_id="branch_reindex",
        python_callable=branch_should_reindex,
    )

    reindex_qdrant = PythonOperator(
        task_id="reindex_qdrant",
        python_callable=task_reindex_qdrant,
        execution_timeout=timedelta(minutes=10),
    )

    skip_reindex = EmptyOperator(task_id="skip_reindex")

    check_critiques = PythonOperator(
        task_id="check_critiques",
        python_callable=task_check_critiques,
        trigger_rule="none_failed_min_one_success",  # Exécuter même si branche skippée
    )

    # ── Dépendances
    start >> health_check >> refresh_events >> branch_reindex
    branch_reindex >> reindex_qdrant >> check_critiques >> end
    branch_reindex >> skip_reindex   >> check_critiques
