"""
InsureDecide — Service Prévisions Temporelles
Méthodes : Holt-Winters (principal) → Régression poly+saisonnalité (fallback)
Prophet et SARIMA exclus : incompatibilités versions + intervalles instables
"""

import os
import logging
import psycopg2
import pandas as pd
import numpy as np
from decimal import Decimal

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://insuredecide_user:insuredecide_pass@postgres:5432/insuredecide"
)

# Bornes métier réalistes par indicateur
BOUNDS = {
    "ratio_combine_pct":    (60.0,   180.0),
    "primes_acquises_tnd":  (100_000, None),
    "cout_sinistres_tnd":   (10_000,  None),
    "nb_sinistres":         (5,       None),
}


def _clean(val):
    if isinstance(val, Decimal):
        return float(val)
    return float(val) if val else 0.0


def _clip_yhat(values: np.ndarray, indicateur: str) -> np.ndarray:
    """Applique les bornes métier uniquement sur yhat (pas sur les intervalles)."""
    lo, hi = BOUNDS.get(indicateur, (0, None))
    result = np.maximum(values, lo) if lo is not None else values
    result = np.minimum(result, hi) if hi is not None else result
    return result


def _forecast_holtwinters(df: pd.DataFrame, nb_mois: int, indicateur: str):
    """
    Holt-Winters avec tendance amortie.
    - Trend amorti : empêche l'extrapolation explosive
    - Intervalles basés sur std des 12 derniers résidus uniquement
    - Croissance linéaire de l'incertitude avec l'horizon
    """
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        import warnings
        warnings.filterwarnings("ignore")

        y = df["y"].values
        n = len(y)

        if n < 24:
            raise ValueError(f"Données insuffisantes : {n} mois (min 24)")

        model = ExponentialSmoothing(
            y,
            seasonal_periods=12,
            trend="add",
            seasonal="add",
            damped_trend=True,      # crucial : amortit la tendance dans le futur
            initialization_method="estimated",
        )
        result = model.fit(optimized=True, remove_bias=True)

        yhat_future = np.array(result.forecast(nb_mois))
        yhat_hist   = np.array(result.fittedvalues)
        resid       = y - yhat_hist

        # Std sur les 12 derniers résidus = volatilité récente
        std_recent = np.std(resid[-12:]) if n >= 12 else np.std(resid)

        last_date    = df["ds"].max()
        future_dates = pd.date_range(
            start=last_date + pd.DateOffset(months=1),
            periods=nb_mois, freq="MS"
        )

        # Intervalles : ±1.96*std pour historique, croissance sqrt pour futur
        hist_ci    = 1.96 * std_recent
        future_ci  = np.array([1.96 * std_recent * np.sqrt(1 + i * 0.15)
                                for i in range(1, nb_mois + 1)])

        all_ds     = pd.concat([df["ds"], pd.Series(future_dates)], ignore_index=True)
        all_yhat   = np.concatenate([yhat_hist, yhat_future])
        all_lower  = np.concatenate([yhat_hist - hist_ci, yhat_future - future_ci])
        all_upper  = np.concatenate([yhat_hist + hist_ci, yhat_future + future_ci])

        fc = pd.DataFrame({
            "ds":         all_ds,
            "yhat":       _clip_yhat(all_yhat, indicateur),
            "yhat_lower": all_lower,   # intervalles libres
            "yhat_upper": all_upper,
        })

        logger.info(f"[HoltWinters] {indicateur} : std_recent={std_recent:.2f}, "
                    f"prévision J+1={yhat_future[0]:.2f}")
        return fc, "Holt-Winters (trend amorti)"

    except Exception as e:
        logger.warning(f"Holt-Winters indisponible ({e}), fallback régression poly")
        return None, None


def _forecast_poly(df: pd.DataFrame, nb_mois: int, indicateur: str):
    """
    Fallback : Ridge polynomial degré 2 + saisonnalité sin/cos (3 harmoniques).
    Entraîné sur les 24 derniers mois pour capter la dynamique récente.
    """
    from sklearn.linear_model import Ridge
    import warnings
    warnings.filterwarnings("ignore")

    # Utiliser les 24 derniers mois pour la régression
    df_fit = df.tail(24).reset_index(drop=True).copy()
    n      = len(df_fit)

    df_fit["t"]  = np.arange(n, dtype=float)
    df_fit["t2"] = df_fit["t"] ** 2
    df_fit["m"]  = df_fit["ds"].dt.month.astype(float)

    for k in range(1, 4):
        df_fit[f"s{k}"] = np.sin(2 * np.pi * k * df_fit["m"] / 12)
        df_fit[f"c{k}"] = np.cos(2 * np.pi * k * df_fit["m"] / 12)

    feats = ["t", "t2", "s1", "c1", "s2", "c2", "s3", "c3"]
    X     = df_fit[feats].values
    y     = df_fit["y"].values

    # Alpha fort pour ratio (régresser vers moyenne) faible pour autres
    alpha = 50.0 if indicateur == "ratio_combine_pct" else 1.0
    reg   = Ridge(alpha=alpha).fit(X, y)

    resid      = y - reg.predict(X)
    std_resid  = np.std(resid)

    last_date    = df["ds"].max()
    future_dates = pd.date_range(
        start=last_date + pd.DateOffset(months=1),
        periods=nb_mois, freq="MS"
    )

    t_fut  = np.arange(n, n + nb_mois, dtype=float)
    m_fut  = future_dates.month.astype(float)
    X_fut  = np.column_stack([
        t_fut, t_fut**2,
        *[np.sin(2 * np.pi * k * m_fut / 12) for k in range(1, 4)],
        *[np.cos(2 * np.pi * k * m_fut / 12) for k in range(1, 4)],
    ])

    yhat_future = reg.predict(X_fut)
    yhat_hist   = reg.predict(X)

    future_ci = np.array([1.96 * std_resid * np.sqrt(1 + i * 0.15)
                           for i in range(1, nb_mois + 1)])

    # Pour l'historique complet (pas seulement les 24 derniers)
    n_full   = len(df)
    n_ancien = n_full - n  # points avant les 24 derniers

    all_ds    = pd.concat([df["ds"], pd.Series(future_dates)], ignore_index=True)
    # Points anciens : valeurs réelles (pas de prédiction)
    all_yhat  = np.concatenate([df["y"].values[:n_ancien], yhat_hist, yhat_future])
    all_lower = np.concatenate([
        df["y"].values[:n_ancien],
        yhat_hist - 1.96 * std_resid,
        yhat_future - future_ci,
    ])
    all_upper = np.concatenate([
        df["y"].values[:n_ancien],
        yhat_hist + 1.96 * std_resid,
        yhat_future + future_ci,
    ])

    fc = pd.DataFrame({
        "ds":         all_ds,
        "yhat":       _clip_yhat(all_yhat, indicateur),
        "yhat_lower": all_lower,
        "yhat_upper": all_upper,
    })

    logger.info(f"[PolyReg] {indicateur} : std={std_resid:.2f}, "
                f"prévision J+1={yhat_future[0]:.2f}")
    return fc, "Régression poly+saisonnalité"


def _run_forecast(df: pd.DataFrame, nb_mois: int, indicateur: str):
    """Holt-Winters → Régression poly (fallback)."""
    fc, methode = _forecast_holtwinters(df, nb_mois, indicateur)
    if fc is not None:
        return fc, methode
    return _forecast_poly(df, nb_mois, indicateur)


def get_forecast(
    departement: str = "Automobile",
    indicateur: str  = "primes_acquises_tnd",
    nb_mois: int     = 6,
) -> dict:
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    indicateurs_valides = {
        "primes_acquises_tnd", "cout_sinistres_tnd",
        "nb_sinistres", "ratio_combine_pct"
    }
    if indicateur not in indicateurs_valides:
        return {"error": f"Indicateur invalide: {indicateur}"}

    cur.execute("""
        SELECT annee, mois, {ind}
        FROM kpis_mensuels
        WHERE departement = %s
        ORDER BY annee, mois
    """.format(ind=indicateur), [departement])

    rows = cur.fetchall()
    cur.close()
    conn.close()

    if len(rows) < 24:
        return {"error": "Données insuffisantes (minimum 24 mois requis)"}

    df       = pd.DataFrame(rows, columns=["annee", "mois", "y"])
    df["ds"] = pd.to_datetime(
        df.apply(lambda r: f"{int(r.annee)}-{int(r.mois):02d}-01", axis=1)
    )
    df["y"]  = df["y"].apply(_clean)

    # Pour ratio_combine_pct : utiliser seulement 2022-2024
    # Les données 2020-2021 sont une phase de transition (150-400%)
    # qui biaise les modèles de prévision vers une tendance haussière fausse
    if indicateur == "ratio_combine_pct":
        df_model = df[df["annee"] >= 2022].reset_index(drop=True)
        if len(df_model) < 24:
            df_model = df.tail(24).reset_index(drop=True)
        logger.info(f"[Forecast] ratio_combine_pct : {len(df_model)} mois utilisés (>= 2022)")
    else:
        df_model = df

    forecast, methode = _run_forecast(df_model, nb_mois, indicateur)

    historique = [
        {
            "periode": row.ds.strftime("%Y-%m"),
            "valeur":  round(float(row.y), 2),
            "type":    "reel",
        }
        for _, row in df.iterrows()
    ]

    ds_max      = df_model["ds"].max()
    future_rows = forecast[forecast["ds"] > ds_max]

    previsions = [
        {
            "periode":    row.ds.strftime("%Y-%m"),
            "valeur":     round(float(row.yhat), 2),
            "valeur_min": round(float(row.yhat_lower), 1),
            "valeur_max": round(float(row.yhat_upper), 1),
            "type":       "prevision",
        }
        for _, row in future_rows.iterrows()
    ]

    dernier_reel  = float(df["y"].iloc[-1])  # dernière valeur réelle (historique complet)
    premiere_prev = previsions[0]["valeur"] if previsions else dernier_reel
    tendance      = ("hausse" if premiere_prev > dernier_reel * 1.02 else
                     "baisse" if premiere_prev < dernier_reel * 0.98 else "stable")
    variation_pct = round(
        (premiere_prev - dernier_reel) / dernier_reel * 100, 1
    ) if dernier_reel else 0

    return {
        "departement":      departement,
        "indicateur":       indicateur,
        "nb_mois":          nb_mois,
        "methode":          methode,
        "historique":       historique[-24:],
        "previsions":       previsions,
        "tendance":         tendance,
        "variation_pct":    variation_pct,
        "derniere_valeur":  round(dernier_reel, 2),
        "prochaine_valeur": round(premiere_prev, 2),
    }


def get_all_forecasts(nb_mois: int = 6) -> dict:
    departements = ["Automobile", "Vie", "Immobilier"]
    indicateurs  = ["primes_acquises_tnd", "cout_sinistres_tnd", "nb_sinistres"]
    results = {}
    for dept in departements:
        results[dept] = {}
        for ind in indicateurs:
            try:
                results[dept][ind] = get_forecast(dept, ind, nb_mois)
            except Exception as e:
                logger.error(f"Erreur {dept}/{ind}: {e}")
                results[dept][ind] = {"error": str(e)}
    return results