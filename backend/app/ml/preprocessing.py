"""
InsureDecide — Data Preprocessing Pipeline
FIX OVERFITTING :
- Suppression nb_suspicions_fraude des features fraude (data leakage)
- Suppression ratio_combine_pct des features résiliation (trop corrélé)
- Régularisation renforcée
- Cross-validation 5-fold comme métrique principale
"""

import os
import logging
import psycopg2
import pandas as pd
import numpy as np
from decimal import Decimal
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import joblib

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://insuredecide_user:insuredecide_pass@postgres:5432/insuredecide"
)

SCALER_PATH = "/app/models/scaler.pkl"

# ── Features par modèle (sans leakage) ────────────────────
#
# RÉSILIATION : on prédit si taux_resiliation >= 15%
# → On EXCLUT taux_resiliation_pct (c'est la target)
# → On RÉDUIT ratio_combine_pct (très corrélé car ratio = sinistres/primes)
# → Features économiques et contextuelles uniquement
FEATURES_RESILIATION = [
    "primes_acquises_tnd",
    "cout_sinistres_tnd",
    "nb_sinistres",
    "provision_totale_tnd",
    "nb_suspicions_fraude",   # OK ici — pas la target résiliation
    "dept_code",
    "mois",
    "trimestre",
    # Features dérivées
    "loss_ratio",             # coût/prime — indicateur pression sinistres
    "cout_moyen_sinistre",    # coût moyen — gravité des sinistres
    "provision_ratio",        # provisions/primes — prudence actuarielle
]

# FRAUDE : on prédit si nb_suspicions_fraude >= 5
# → On EXCLUT nb_suspicions_fraude (c'est la target — leakage direct)
# → On EXCLUT taux_fraude (= nb_suspicions / nb_sinistres — leakage indirect)
# → Features comportementales et financières uniquement
FEATURES_FRAUDE = [
    "primes_acquises_tnd",
    "cout_sinistres_tnd",
    "nb_sinistres",
    "provision_totale_tnd",
    "ratio_combine_pct",
    "dept_code",
    "mois",
    "trimestre",
    # Features dérivées (sans taux_fraude)
    "loss_ratio",
    "cout_moyen_sinistre",
    "provision_ratio",
]


def _clean_val(val):
    if isinstance(val, Decimal):
        return float(val)
    return float(val) if val is not None else 0.0


def load_raw_data() -> pd.DataFrame:
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()
    cur.execute("""
        SELECT annee, mois, departement,
               ratio_combine_pct, primes_acquises_tnd, cout_sinistres_tnd,
               nb_sinistres, taux_resiliation_pct, provision_totale_tnd,
               nb_suspicions_fraude
        FROM kpis_mensuels
        ORDER BY departement, annee, mois
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    df = pd.DataFrame(rows, columns=[
        "annee", "mois", "departement",
        "ratio_combine_pct", "primes_acquises_tnd", "cout_sinistres_tnd",
        "nb_sinistres", "taux_resiliation_pct", "provision_totale_tnd",
        "nb_suspicions_fraude"
    ])

    numeric_cols = [
        "ratio_combine_pct", "primes_acquises_tnd", "cout_sinistres_tnd",
        "nb_sinistres", "taux_resiliation_pct", "provision_totale_tnd",
        "nb_suspicions_fraude"
    ]
    for col in numeric_cols:
        df[col] = df[col].apply(_clean_val)

    logger.info(f"[Preprocessing] Données chargées : {len(df)} lignes")
    return df


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pipeline complet de nettoyage :
    1. Suppression NaN critiques
    2. Filtre temporel 2021+
    3. Filtres métier (bornes domaine assurance)
    4. Winsorization IQR x1.5 PAR DÉPARTEMENT
    5. Imputation médiane pour NaN résiduels
    """
    initial_len = len(df)

    # Étape 1 : Suppression NaN critiques
    df = df.dropna(subset=["ratio_combine_pct", "primes_acquises_tnd", "nb_sinistres"])

    # Étape 2 : Filtre temporel (2020 = données de démarrage aberrantes)
    df = df[df["annee"] >= 2021].copy()

    # Étape 3 : Filtres métier - bornes domaine assurance
    BOUNDS = {
        "ratio_combine_pct":    (0,    500),
        "primes_acquises_tnd":  (1000, None),
        "cout_sinistres_tnd":   (0,    None),
        "nb_sinistres":         (0,    None),
        "taux_resiliation_pct": (0,    100),
        "nb_suspicions_fraude": (0,    None),
        "provision_totale_tnd": (0,    None),
    }
    for col, (low, high) in BOUNDS.items():
        if col not in df.columns:
            continue
        if low is not None:
            df = df[df[col] >= low]
        if high is not None:
            df = df[df[col] <= high]

    # Étape 4 : Winsorization IQR x1.5 PAR DÉPARTEMENT
    # Traitement séparé pour éviter pollution croisée entre départements
    COLS_WINSOR = [
        "ratio_combine_pct", "primes_acquises_tnd", "cout_sinistres_tnd",
        "nb_sinistres", "taux_resiliation_pct", "provision_totale_tnd",
        "nb_suspicions_fraude",
    ]
    depts = df["departement"].unique()
    df_parts = []
    for dept in depts:
        mask   = df["departement"] == dept
        df_dep = df[mask].copy()
        for col in COLS_WINSOR:
            if col not in df_dep.columns:
                continue
            Q1  = df_dep[col].quantile(0.25)
            Q3  = df_dep[col].quantile(0.75)
            IQR = Q3 - Q1
            lower = Q1 - 1.5 * IQR
            upper = Q3 + 1.5 * IQR
            n_clipped = ((df_dep[col] < lower) | (df_dep[col] > upper)).sum()
            df_dep[col] = df_dep[col].clip(lower=lower, upper=upper)
            if n_clipped > 0:
                logger.info(f"[Preprocessing] {dept}/{col} : {n_clipped} valeurs winsorisees [{lower:.1f}, {upper:.1f}]")
        df_parts.append(df_dep)
    df = pd.concat(df_parts, ignore_index=True)

    # Étape 5 : Imputation médiane pour NaN résiduels
    for col in COLS_WINSOR:
        if col not in df.columns:
            continue
        n_nan = df[col].isna().sum()
        if n_nan > 0:
            median_val = df[col].median()
            df[col] = df[col].fillna(median_val)
            logger.info(f"[Preprocessing] {col} : {n_nan} NaN imputés par médiane ({median_val:.2f})")

    logger.info(f"[Preprocessing] Nettoyage complet : {initial_len} -> {len(df)} lignes ({initial_len - len(df)} supprimees)")
    return df


def feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    df["loss_ratio"]          = df["cout_sinistres_tnd"] / (df["primes_acquises_tnd"] + 1)
    df["cout_moyen_sinistre"] = df["cout_sinistres_tnd"] / (df["nb_sinistres"] + 1)
    df["taux_fraude"]         = df["nb_suspicions_fraude"] / (df["nb_sinistres"] + 1)
    df["provision_ratio"]     = df["provision_totale_tnd"] / (df["primes_acquises_tnd"] + 1)
    df["trimestre"]           = ((df["mois"] - 1) // 3) + 1
    logger.info("[Preprocessing] Feature engineering : 5 features dérivées ajoutées")
    return df


def encode_data(df: pd.DataFrame) -> pd.DataFrame:
    dept_map = {"Automobile": 0, "Vie": 1, "Immobilier": 2}
    df["dept_code"] = df["departement"].map(dept_map).fillna(0).astype(int)
    return df


def build_targets(df: pd.DataFrame) -> pd.DataFrame:
    df["target_resiliation"] = (df["taux_resiliation_pct"] >= 15).astype(int)
    df["target_fraude"]      = (df["nb_suspicions_fraude"] >= 5).astype(int)

    logger.info(
        f"[Preprocessing] Résiliation critique : {df['target_resiliation'].sum()} cas "
        f"({df['target_resiliation'].mean()*100:.1f}%) | "
        f"Fraude : {df['target_fraude'].sum()} cas ({df['target_fraude'].mean()*100:.1f}%)"
    )
    return df


def scale_features(X_train, X_test, save=True):
    scaler         = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    if save:
        os.makedirs("/app/models", exist_ok=True)
        joblib.dump(scaler, SCALER_PATH)
        logger.info(f"[Preprocessing] Scaler sauvegardé : {SCALER_PATH}")

    return X_train_scaled, X_test_scaled, scaler


def run_preprocessing(target: str = "resiliation", use_extended_features: bool = True):
    """
    Pipeline complet avec features anti-leakage selon le modèle cible.
    """
    df = load_raw_data()
    df = clean_data(df)
    df = feature_engineering(df)
    df = encode_data(df)
    df = build_targets(df)

    # Sélection features sans leakage selon le modèle
    if target == "fraude":
        feature_names = [f for f in FEATURES_FRAUDE if f in df.columns]
    else:
        feature_names = [f for f in FEATURES_RESILIATION if f in df.columns]

    target_col = f"target_{target}"
    if target_col not in df.columns:
        raise ValueError(f"Target inconnue : {target_col}")

    X = df[feature_names].values
    y = df[target_col].values

    # Vérification distribution des classes
    n_pos = y.sum()
    n_neg = (y == 0).sum()
    logger.info(f"[Preprocessing] Distribution {target}: {n_pos} positifs / {n_neg} négatifs")

    if n_pos < 5 or n_neg < 5:
        logger.warning(f"[Preprocessing] ⚠️ Très peu de cas positifs ({n_pos}) — modèle peu fiable")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    X_train_scaled, X_test_scaled, scaler = scale_features(X_train, X_test, save=True)

    stats = {
        "nb_total":            len(df),
        "nb_train":            len(X_train),
        "nb_test":             len(X_test),
        "nb_features":         len(feature_names),
        "features":            feature_names,
        "target":              target,
        "classe_positive":     int(n_pos),
        "classe_negative":     int(n_neg),
        "ratio_desequilibre":  round(float(n_neg / max(n_pos, 1)), 2),
        "annees_couvertes":    sorted(df["annee"].unique().tolist()),
        "leakage_prevention":  True,
        "features_exclues_fraude":      ["nb_suspicions_fraude", "taux_fraude"],
        "features_exclues_resiliation": ["taux_resiliation_pct"],
    }

    return X_train_scaled, X_test_scaled, y_train, y_test, feature_names, scaler, stats


def preprocess_single(input_values: dict, target: str = "resiliation") -> tuple:
    """
    Préprocesse un seul enregistrement pour l'inférence.
    Utilise les mêmes features que l'entraînement selon le modèle.
    """
    # Feature engineering
    primes   = input_values.get("primes_acquises_tnd", 1) or 1
    sinistres = input_values.get("nb_sinistres", 1) or 1
    cout     = input_values.get("cout_sinistres_tnd", 0)
    prov     = input_values.get("provision_totale_tnd", 0)
    susp     = input_values.get("nb_suspicions_fraude", 0)
    mois     = int(input_values.get("mois", 1))

    input_values["loss_ratio"]          = cout / (primes + 1)
    input_values["cout_moyen_sinistre"] = cout / (sinistres + 1)
    input_values["taux_fraude"]         = susp / (sinistres + 1)
    input_values["provision_ratio"]     = prov / (primes + 1)
    input_values["trimestre"]           = ((mois - 1) // 3) + 1

    # Sélectionner les bonnes features selon le modèle
    if target == "fraude":
        feature_names = [f for f in FEATURES_FRAUDE]
    else:
        feature_names = [f for f in FEATURES_RESILIATION]

    X = np.array([[input_values.get(f, 0.0) for f in feature_names]])

    if os.path.exists(SCALER_PATH):
        scaler = joblib.load(SCALER_PATH)
        try:
            X = scaler.transform(X)
        except Exception:
            pass  # Si dimensions incompatibles, on continue sans scaler
    else:
        logger.warning("[Preprocessing] Scaler non trouvé — inférence sans normalisation")

    return X, feature_names


def get_preprocessing_report() -> dict:
    try:
        df_raw   = load_raw_data()
        df_clean = clean_data(df_raw.copy())
        df_fe    = feature_engineering(df_clean.copy())
        df_enc   = encode_data(df_fe.copy())
        df_tgt   = build_targets(df_enc.copy())

        return {
            "etapes": [
                {
                    "etape": "1. Chargement",
                    "description": "Extraction depuis PostgreSQL (kpis_mensuels)",
                    "nb_lignes": len(df_raw),
                    "nb_colonnes": len(df_raw.columns),
                },
                {
                    "etape": "2. Nettoyage",
                    "description": "Suppression NaN | Filtre 2021+ | Bornes métier assurance | Winsorization IQR x1.5 par département | Imputation médiane",
                    "nb_lignes": len(df_clean),
                    "lignes_supprimees": len(df_raw) - len(df_clean),
                    "details": {
                        "filtre_temporel": "annee >= 2021 (2020 = bruit cumulatif)",
                        "filtres_metier": "ratio_combine_pct in [0,500] | primes >= 1000 | taux_resiliation in [0,100]",
                        "winsorization": "IQR x1.5 par département (Automobile / Vie / Immobilier séparément)",
                        "imputation": "Médiane par colonne pour NaN résiduels",
                    },
                },
                {
                    "etape": "3. Feature Engineering",
                    "description": "5 features dérivées calculées",
                    "features_ajoutees": ["loss_ratio", "cout_moyen_sinistre", "taux_fraude", "provision_ratio", "trimestre"],
                },
                {
                    "etape": "4. Encodage",
                    "description": "Label encoding : departement → dept_code",
                    "mapping": {"Automobile": 0, "Vie": 1, "Immobilier": 2},
                },
                {
                    "etape": "5. Targets",
                    "description": "Variables cibles binaires",
                    "target_resiliation": {
                        "condition": "taux_resiliation_pct >= 15%",
                        "nb_positifs": int(df_tgt["target_resiliation"].sum()),
                        "pct_positifs": round(float(df_tgt["target_resiliation"].mean() * 100), 1),
                    },
                    "target_fraude": {
                        "condition": "nb_suspicions_fraude >= 5",
                        "nb_positifs": int(df_tgt["target_fraude"].sum()),
                        "pct_positifs": round(float(df_tgt["target_fraude"].mean() * 100), 1),
                    },
                },
                {
                    "etape": "6. Anti-leakage",
                    "description": "Features exclues pour éviter la fuite de données",
                    "fraude_exclues":      ["nb_suspicions_fraude (= target)", "taux_fraude (= target / nb_sinistres)"],
                    "resiliation_exclues": ["taux_resiliation_pct (= target)"],
                },
                {
                    "etape": "7. Normalisation",
                    "description": "StandardScaler (mean=0, std=1) — fit sur train uniquement",
                    "split": "80% train / 20% test (stratifié)",
                },
            ],
            "features_resiliation": FEATURES_RESILIATION,
            "features_fraude":      FEATURES_FRAUDE,
            "nb_features_resiliation": len(FEATURES_RESILIATION),
            "nb_features_fraude":      len(FEATURES_FRAUDE),
            "periode_couverte": f"{int(df_clean['annee'].min())} – {int(df_clean['annee'].max())}",
            "nb_observations_finales": len(df_tgt),
        }
    except Exception as e:
        return {"error": str(e)}