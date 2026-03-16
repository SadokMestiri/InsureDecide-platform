"""
InsureDecide — Service SHAP
Calcule les valeurs SHAP pour expliquer les prédictions des modèles ML.
FIX : KeyError pipeline, NoneType scaler, probability déjà en %
"""

import os
import logging
import numpy as np
import joblib
import shap

logger = logging.getLogger(__name__)

MODELS_DIR = "/app/models"

FEATURE_LABELS = {
    "ratio_combine_pct":    "Ratio Combiné (%)",
    "primes_acquises_tnd":  "Primes Acquises (TND)",
    "cout_sinistres_tnd":   "Coût Sinistres (TND)",
    "nb_sinistres":         "Nombre de Sinistres",
    "provision_totale_tnd": "Provisions (TND)",
    "nb_suspicions_fraude": "Suspicions Fraude",
    "dept_code":            "Département",
    "mois":                 "Mois",
    "annee":                "Année",
    "loss_ratio":           "Loss Ratio (Coût/Prime)",
    "cout_moyen_sinistre":  "Coût Moyen Sinistre",
    "taux_fraude":          "Taux de Fraude",
    "provision_ratio":      "Ratio Provision/Prime",
    "trimestre":            "Trimestre",
}


def _load_model(model_name: str) -> tuple:
    """
    Charge le pkl et retourne (clf, features, scaler).
    Compatible ancien format pipeline ET nouveau format {model, features, scaler}.
    """
    path = f"{MODELS_DIR}/{model_name}_model.pkl"
    if not os.path.exists(path):
        raise FileNotFoundError(f"Modèle {model_name} non trouvé — lancez /api/ml/train d'abord")

    data = joblib.load(path)

    # Nouveau format : dict avec clés "model", "features", "scaler"
    if isinstance(data, dict):
        clf      = data.get("model") or data.get("pipeline") or data.get("clf")
        features = data.get("features", [])
        scaler   = data.get("scaler")

        # Si clf est encore un pipeline sklearn, extraire le vrai clf
        if hasattr(clf, "named_steps"):
            scaler = scaler or clf.named_steps.get("scaler")
            clf    = clf.named_steps.get("clf", clf)

        return clf, features, scaler

    # Ancien format : pipeline directement
    if hasattr(data, "named_steps"):
        clf    = data.named_steps.get("clf", data)
        scaler = data.named_steps.get("scaler")
        return clf, [], scaler

    # Format inconnu : on essaie de l'utiliser directement
    return data, [], None


def _get_shap_values_for_class1(explainer, X):
    """Extrait les valeurs SHAP pour la classe 1 quel que soit le format."""
    sv = explainer.shap_values(X)
    if isinstance(sv, list):
        # RandomForest : liste [sv_classe0, sv_classe1]
        return sv[1]
    elif hasattr(sv, 'shape') and len(sv.shape) == 3:
        # (n_samples, n_features, n_classes)
        return sv[:, :, 1]
    else:
        # GradientBoosting : (n_samples, n_features) déjà pour classe 1
        return sv


def explain_prediction(model_name: str, input_values: dict) -> dict:
    """
    Calcule les valeurs SHAP pour une prédiction donnée.
    """
    clf, features, scaler = _load_model(model_name)

    if not features:
        return {"error": "Modèle sans liste de features — relancez l'entraînement"}

    # Preprocessing via preprocess_single
    try:
        from app.ml.preprocessing import preprocess_single
        X_scaled, features = preprocess_single(input_values)
    except Exception as e:
        logger.error(f"Erreur preprocess_single: {e}")
        # Fallback : construire X manuellement depuis input_values
        X_raw = np.array([[input_values.get(f, 0) for f in features]], dtype=float)
        X_scaled = scaler.transform(X_raw) if scaler is not None else X_raw

    # Prédiction
    prediction  = int(clf.predict(X_scaled)[0])
    probability = float(clf.predict_proba(X_scaled)[0][1])  # 0.0 à 1.0

    # SHAP
    try:
        explainer   = shap.TreeExplainer(clf)
        sv_all      = _get_shap_values_for_class1(explainer, X_scaled)
        sv          = sv_all[0]  # première (et seule) ligne

        base_val = explainer.expected_value
        if isinstance(base_val, (list, np.ndarray)):
            base_val = float(base_val[1]) if len(base_val) > 1 else float(base_val[0])
        else:
            base_val = float(base_val)
    except Exception as e:
        logger.error(f"Erreur SHAP TreeExplainer: {e}")
        sv       = np.zeros(len(features))
        base_val = 0.0

    # Contributions SHAP
    contributions = []
    for i, feat in enumerate(features):
        val      = float(input_values.get(feat, X_scaled[0][i] if i < X_scaled.shape[1] else 0))
        shap_val = float(sv[i]) if i < len(sv) else 0.0
        contributions.append({
            "feature":    feat,
            "label":      FEATURE_LABELS.get(feat, feat.replace("_", " ").title()),
            "value":      round(val, 2),
            "shap_value": round(shap_val, 4),
            "impact":     "hausse_risque" if shap_val > 0 else "baisse_risque",
            "abs_impact": round(abs(shap_val), 4),
        })

    contributions.sort(key=lambda x: x["abs_impact"], reverse=True)

    top3     = contributions[:3]
    facteurs = ", ".join([
        f"{c['label']} ({'+' if c['shap_value'] > 0 else ''}{c['shap_value']:.3f})"
        for c in top3
    ])

    if model_name == "resiliation":
        label_pos = "Résiliation critique probable (> 15%)"
        label_neg = "Résiliation dans les normes (< 15%)"
    else:
        label_pos = "Risque de fraude élevé (≥ 5 suspicions)"
        label_neg = "Risque de fraude faible"

    return {
        "model":         model_name,
        "prediction":    prediction,
        "label":         label_pos if prediction == 1 else label_neg,
        "probability":   round(probability * 100, 1),   # retourné en %
        "risque":        "élevé" if probability > 0.6 else "modéré" if probability > 0.4 else "faible",
        "explication":   f"Les 3 facteurs principaux : {facteurs}",
        "contributions": contributions,
        "base_value":    round(base_val, 4),
    }


def get_global_importance(model_name: str) -> dict:
    """
    Retourne l'importance globale des features via SHAP mean(|SHAP|).
    """
    clf, features, scaler = _load_model(model_name)

    if not features:
        return {"model": model_name, "importance": []}

    np.random.seed(42)
    n = 50
    ranges = {
        "ratio_combine_pct":    (70, 130),
        "primes_acquises_tnd":  (500000, 2000000),
        "cout_sinistres_tnd":   (300000, 1500000),
        "nb_sinistres":         (50, 300),
        "provision_totale_tnd": (100000, 800000),
        "nb_suspicions_fraude": (0, 15),
        "dept_code":            (0, 2),
        "mois":                 (1, 12),
        "annee":                (2020, 2024),
        "loss_ratio":           (0.3, 1.5),
        "cout_moyen_sinistre":  (2000, 15000),
        "taux_fraude":          (0, 0.15),
        "provision_ratio":      (0.1, 0.6),
        "trimestre":            (1, 4),
    }

    X_bg = np.column_stack([
        np.random.uniform(ranges.get(f, (0, 1))[0], ranges.get(f, (0, 1))[1], n)
        for f in features
    ])

    # Appliquer scaler si disponible
    if scaler is not None:
        try:
            X_scaled = scaler.transform(X_bg)
        except Exception:
            X_scaled = X_bg
    else:
        X_scaled = X_bg

    try:
        explainer   = shap.TreeExplainer(clf)
        sv_all      = _get_shap_values_for_class1(explainer, X_scaled)
        mean_abs    = np.abs(sv_all).mean(axis=0)
    except Exception as e:
        logger.error(f"Erreur SHAP importance: {e}")
        # Fallback : utiliser feature_importances_ du modèle
        if hasattr(clf, "feature_importances_"):
            mean_abs = clf.feature_importances_
        else:
            mean_abs = np.ones(len(features))

    total = mean_abs.sum()

    importance = []
    for i, feat in enumerate(features):
        importance.append({
            "feature":    feat,
            "label":      FEATURE_LABELS.get(feat, feat.replace("_", " ").title()),
            "importance": round(float(mean_abs[i]), 4),
            "pct":        round(float(mean_abs[i] / total * 100), 1) if total > 0 else 0,
        })

    importance.sort(key=lambda x: x["importance"], reverse=True)

    return {
        "model":      model_name,
        "importance": importance,
    }