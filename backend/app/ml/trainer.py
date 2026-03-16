"""
InsureDecide — ML Trainer
FIX OVERFITTING :
- Régularisation renforcée (max_depth réduit, min_samples_leaf augmenté)
- Cross-validation comme métrique principale
- Features sans leakage via preprocessing.py
"""

import os
import logging
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
import joblib

logger     = logging.getLogger(__name__)
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
MODELS_DIR = "/app/models"
os.makedirs(MODELS_DIR, exist_ok=True)


def train_resiliation_model() -> dict:
    from app.ml.preprocessing import run_preprocessing

    X_train, X_test, y_train, y_test, features, scaler, stats = run_preprocessing("resiliation")

    # Régularisation renforcée pour éviter overfitting sur 144 lignes
    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=4,           # réduit vs 6 avant
        min_samples_leaf=5,    # augmenté vs 3 avant — force généralisation
        min_samples_split=10,  # nouveau — évite splits sur trop peu de données
        max_features="sqrt",
        random_state=42,
        class_weight="balanced",
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    y_prob = clf.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    f1  = f1_score(y_test, y_pred, zero_division=0)
    auc = roc_auc_score(y_test, y_prob) if len(set(y_test)) > 1 else 0.5

    # Cross-validation 5-fold sur train (métrique principale)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_auc  = cross_val_score(clf, X_train, y_train, cv=cv, scoring="roc_auc").mean()
    cv_f1   = cross_val_score(clf, X_train, y_train, cv=cv, scoring="f1").mean()

    # Alerte overfitting
    gap = auc - cv_auc
    if gap > 0.15:
        logger.warning(f"⚠️ Overfitting détecté résiliation : test AUC={auc:.3f} vs CV AUC={cv_auc:.3f} (gap={gap:.3f})")

    model_path = f"{MODELS_DIR}/resiliation_model.pkl"
    joblib.dump({"model": clf, "features": features, "scaler": scaler}, model_path)

    try:
        mlflow.set_tracking_uri(MLFLOW_URI)
        mlflow.set_experiment("InsureDecide_Resiliation")
        with mlflow.start_run(run_name="RandomForest_Resiliation_v2"):
            mlflow.log_params({
                "model": "RandomForestClassifier",
                "n_estimators": 200, "max_depth": 4,
                "min_samples_leaf": 5, "min_samples_split": 10,
                "nb_features": len(features),
                "leakage_prevention": True,
                "annees": str(stats["annees_couvertes"]),
            })
            mlflow.log_metrics({
                "accuracy":    round(acc, 4),
                "f1_score":    round(f1, 4),
                "roc_auc":     round(auc, 4),
                "cv_auc":      round(cv_auc, 4),
                "cv_f1":       round(cv_f1, 4),
                "overfit_gap": round(gap, 4),
            })
            mlflow.sklearn.log_model(clf, "model")
    except Exception as e:
        logger.warning(f"⚠️ MLflow indisponible : {e}")

    return {
        "model":    "resiliation",
        "accuracy": round(acc, 4),
        "f1":       round(f1, 4),
        "auc":      round(auc, 4),
        "cv_auc":   round(cv_auc, 4),
        "cv_f1":    round(cv_f1, 4),
        "overfit_gap": round(gap, 4),
        "features": features,
        "nb_features": len(features),
        "preprocessing_stats": stats,
    }


def train_fraude_model() -> dict:
    from app.ml.preprocessing import run_preprocessing

    X_train, X_test, y_train, y_test, features, scaler, stats = run_preprocessing("fraude")

    # GradientBoosting avec forte régularisation
    clf = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=3,           # réduit vs 4
        learning_rate=0.05,    # réduit vs 0.1 — apprentissage plus lent = moins overfitting
        min_samples_leaf=5,
        subsample=0.8,         # nouveau — bagging pour réduire variance
        max_features="sqrt",   # nouveau — feature sampling
        random_state=42,
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    y_prob = clf.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    f1  = f1_score(y_test, y_pred, zero_division=0)
    auc = roc_auc_score(y_test, y_prob) if len(set(y_test)) > 1 else 0.5

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_auc = cross_val_score(clf, X_train, y_train, cv=cv, scoring="roc_auc").mean()
    cv_f1  = cross_val_score(clf, X_train, y_train, cv=cv, scoring="f1").mean()

    gap = auc - cv_auc
    if gap > 0.15:
        logger.warning(f"⚠️ Overfitting détecté fraude : test AUC={auc:.3f} vs CV AUC={cv_auc:.3f} (gap={gap:.3f})")

    model_path = f"{MODELS_DIR}/fraude_model.pkl"
    joblib.dump({"model": clf, "features": features, "scaler": scaler}, model_path)

    try:
        mlflow.set_tracking_uri(MLFLOW_URI)
        mlflow.set_experiment("InsureDecide_Fraude")
        with mlflow.start_run(run_name="GradientBoosting_Fraude_v2"):
            mlflow.log_params({
                "model": "GradientBoostingClassifier",
                "n_estimators": 100, "max_depth": 3,
                "learning_rate": 0.05, "subsample": 0.8,
                "nb_features": len(features),
                "leakage_prevention": True,
                "features_exclues": "nb_suspicions_fraude, taux_fraude",
            })
            mlflow.log_metrics({
                "accuracy":    round(acc, 4),
                "f1_score":    round(f1, 4),
                "roc_auc":     round(auc, 4),
                "cv_auc":      round(cv_auc, 4),
                "cv_f1":       round(cv_f1, 4),
                "overfit_gap": round(gap, 4),
            })
            mlflow.sklearn.log_model(clf, "model")
    except Exception as e:
        logger.warning(f"⚠️ MLflow indisponible : {e}")

    return {
        "model":    "fraude",
        "accuracy": round(acc, 4),
        "f1":       round(f1, 4),
        "auc":      round(auc, 4),
        "cv_auc":   round(cv_auc, 4),
        "cv_f1":    round(cv_f1, 4),
        "overfit_gap": round(gap, 4),
        "features": features,
        "nb_features": len(features),
        "preprocessing_stats": stats,
    }


def train_all() -> dict:
    logger.info("🚀 Entraînement avec prévention overfitting + anti-leakage...")
    res    = train_resiliation_model()
    fraude = train_fraude_model()
    logger.info("✅ Entraînement terminé")
    return {"status": "success", "resiliation": res, "fraude": fraude}