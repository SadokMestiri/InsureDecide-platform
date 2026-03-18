"""
InsureDecide — Router ML / MLOps

Routes :
  POST /api/ml/train           → Entraîne les 2 modèles + track MLflow
  GET  /api/ml/metrics         → Métriques des modèles entraînés
  POST /api/ml/explain         → Prédiction + SHAP pour un input donné
  GET  /api/ml/importance/{model} → Importance globale des features
  GET  /api/ml/status          → Vérifie si les modèles sont disponibles
"""

import os
import logging
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(tags=["MLOps"])

MODELS_DIR = "/app/models"


class ExplainRequest(BaseModel):
    model:              str    = "resiliation"   # resiliation | fraude
    ratio_combine_pct:  float  = 105.0
    primes_acquises_tnd: float = 1500000.0
    cout_sinistres_tnd: float  = 900000.0
    nb_sinistres:       float  = 150.0
    provision_totale_tnd: float = 300000.0
    nb_suspicions_fraude: float = 3.0
    dept_code:          float  = 0.0             # 0=Auto, 1=Vie, 2=Immo
    mois:               float  = 12.0
    annee:              float  = 2024.0


# ── POST /api/ml/train
@router.post("/api/ml/train")
async def train_models():
    """Lance l'entraînement des 2 modèles ML et les track dans MLflow."""
    try:
        loop   = asyncio.get_event_loop()
        from app.ml.trainer import train_all
        result = await loop.run_in_executor(None, train_all)
        return result
    except Exception as e:
        logger.error(f"Erreur entraînement: {e}")
        return {"status": "error", "detail": str(e)}


# ── GET /api/ml/status
@router.get("/api/ml/status")
def ml_status():
    """Vérifie la disponibilité des modèles entraînés."""
    import joblib
    models = {}
    for name in ["resiliation", "fraude"]:
        path = f"{MODELS_DIR}/{name}_model.pkl"
        if os.path.exists(path):
            data = joblib.load(path)
            models[name] = {
                "available": True,
                "features":  data.get("features", []),
                "path":      path,
            }
        else:
            models[name] = {"available": False}

    return {
        "ready":    all(m["available"] for m in models.values()),
        "models":   models,
        "mlflow":   os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"),
    }


# ── POST /api/ml/explain
@router.post("/api/ml/explain")
async def explain(req: ExplainRequest):
    """Génère une prédiction + explication SHAP pour le modèle demandé."""
    try:
        from app.ml.shap_service import explain_prediction
        input_values = {
            "ratio_combine_pct":    req.ratio_combine_pct,
            "primes_acquises_tnd":  req.primes_acquises_tnd,
            "cout_sinistres_tnd":   req.cout_sinistres_tnd,
            "nb_sinistres":         req.nb_sinistres,
            "provision_totale_tnd": req.provision_totale_tnd,
            "nb_suspicions_fraude": req.nb_suspicions_fraude,
            "dept_code":            req.dept_code,
            "mois":                 req.mois,
            "annee":                req.annee,
        }
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, explain_prediction, req.model, input_values)
        return result
    except FileNotFoundError as e:
        return {"status": "error", "detail": str(e)}
    except Exception as e:
        logger.error(f"Erreur SHAP: {e}")
        return {"status": "error", "detail": str(e)}


# ── GET /api/ml/importance/{model}
@router.get("/api/ml/importance/{model_name}")
async def feature_importance(model_name: str):
    """Retourne l'importance globale des features via SHAP mean(|SHAP|)."""
    try:
        from app.ml.shap_service import get_global_importance
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, get_global_importance, model_name)
        return result
    except FileNotFoundError as e:
        return {"status": "error", "detail": str(e)}
    except Exception as e:
        logger.error(f"Erreur importance: {e}")
        return {"status": "error", "detail": str(e)}


# ── GET /api/ml/presets
@router.get("/api/ml/presets")
def ml_presets():
    """Retourne des cas prédéfinis pour tester l'explicabilité."""
    return {
        "presets": [
            {
                "label":      "Automobile — Décembre 2024 (données réelles)",
                "model":      "resiliation",
                "dept_code":  0,
                "ratio_combine_pct":    88.6,
                "primes_acquises_tnd":  1753651,
                "cout_sinistres_tnd":   969002,
                "nb_sinistres":         183,
                "provision_totale_tnd": 280000,
                "nb_suspicions_fraude": 6,
                "mois": 12, "annee": 2024,
            },
            {
                "label":      "Vie — Décembre 2024 (données réelles)",
                "model":      "fraude",
                "dept_code":  1,
                "ratio_combine_pct":    125.2,
                "primes_acquises_tnd":  1527430,
                "cout_sinistres_tnd":   1211819,
                "nb_sinistres":         30,
                "provision_totale_tnd": 450000,
                "nb_suspicions_fraude": 2,
                "mois": 12, "annee": 2024,
            },
            {
                "label":      "Immobilier — Décembre 2024 (données réelles)",
                "model":      "resiliation",
                "dept_code":  2,
                "ratio_combine_pct":    105.2,
                "primes_acquises_tnd":  898200,
                "cout_sinistres_tnd":   601230,
                "nb_sinistres":         75,
                "provision_totale_tnd": 190000,
                "nb_suspicions_fraude": 1,
                "mois": 12, "annee": 2024,
            },
        ]
    }


# ══════════════════════════════════════════════
# PROPHET — Prévisions temporelles
# ══════════════════════════════════════════════

# ── GET /api/ml/forecast
@router.get("/api/ml/forecast")
async def forecast(
    departement: str = "Automobile",
    indicateur: str = "primes_acquises_tnd",
    nb_mois: int = 6,
):
    """
    Prévisions Prophet pour un département et indicateur donnés.
    indicateur: primes_acquises_tnd | cout_sinistres_tnd | nb_sinistres | ratio_combine_pct
    """
    try:
        from app.ml.prophet_service import get_forecast
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, get_forecast, departement, indicateur, nb_mois)
        return result
    except Exception as e:
        logger.error(f"Erreur Prophet: {e}")
        return {"status": "error", "detail": str(e)}


# ── GET /api/ml/forecast/all
@router.get("/api/ml/forecast/all")
async def forecast_all(nb_mois: int = 6):
    """Prévisions Prophet pour tous les départements et indicateurs clés."""
    try:
        from app.ml.prophet_service import get_all_forecasts
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, get_all_forecasts, nb_mois)
        return result
    except Exception as e:
        logger.error(f"Erreur Prophet all: {e}")
        return {"status": "error", "detail": str(e)}


# ══════════════════════════════════════════════
# ISOLATION FOREST — Détection anomalies
# ══════════════════════════════════════════════

# ── GET /api/ml/anomalies
@router.get("/api/ml/anomalies")
async def detect_anomalies(
    departement: Optional[str] = None,
    contamination: float = 0.1,
):
    """
    Détecte les anomalies dans les KPIs via Isolation Forest.
    departement: Automobile | Vie | Immobilier | None (tous)
    contamination: 0.05 à 0.2 (proportion attendue d'anomalies)
    """
    try:
        from app.ml.anomaly_service import detect_anomalies as _detect
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _detect, departement, contamination)
        return result
    except Exception as e:
        logger.error(f"Erreur Isolation Forest: {e}")
        return {"status": "error", "detail": str(e)}


# ══════════════════════════════════════════════
# EVIDENTLY AI — Data Drift
# ══════════════════════════════════════════════

# ── GET /api/ml/drift
@router.get("/api/ml/drift")
async def detect_drift(
    departement: Optional[str] = None,
    nb_mois_reference: int = 12,
    nb_mois_courant: int = 6,
):
    """
    Détecte le data drift via Evidently AI.
    Compare les nb_mois_courant derniers mois vs les nb_mois_reference mois précédents.
    """
    try:
        from app.ml.drift_service import detect_drift as _drift
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _drift, departement, nb_mois_reference, nb_mois_courant)
        return result
    except Exception as e:
        logger.error(f"Erreur Evidently: {e}")
        return {"status": "error", "detail": str(e)}


# ══════════════════════════════════════════════
# PREPROCESSING — Rapport du pipeline
# ══════════════════════════════════════════════

# ── GET /api/ml/preprocessing
@router.get("/api/ml/preprocessing")
async def preprocessing_report():
    """
    Retourne le rapport complet du pipeline de preprocessing :
    étapes, statistiques, features finales, distribution des targets.
    """
    try:
        from app.ml.preprocessing import get_preprocessing_report
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, get_preprocessing_report)
        return result
    except Exception as e:
        logger.error(f"Erreur preprocessing report: {e}")
        return {"status": "error", "detail": str(e)}


# ══════════════════════════════════════════════
# SEGMENTATION CLIENTS — KMeans
# ══════════════════════════════════════════════

# ── GET /api/ml/segmentation
@router.get("/api/ml/segmentation")
async def segmentation_clients(n_clusters: int = 4, limit_clients: int = 20000):
    """
    Segmentation client par clustering K-Means.
    Retourne les profils de segments et un aperçu des clients clés.
    """
    try:
        from app.ml.segmentation_service import get_client_segmentation
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, get_client_segmentation, n_clusters, limit_clients)
        return result
    except Exception as e:
        logger.error(f"Erreur segmentation: {e}")
        return {"status": "error", "detail": str(e)}