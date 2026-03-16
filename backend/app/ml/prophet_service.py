"""
InsureDecide — Service Prophet
Prévisions temporelles avec fallback robuste multi-méthode.
Ordre : Prophet → SARIMA → Holt-Winters → Régression poly+saisonnalité
"""

import os
import logging
import psycopg2
import pandas as pd
import numpy as np
from decimal import Decimal

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://insuredecide_user:insuredecide_pass@postgres:5432/insuredecide")

INDICATEURS_POSITIFS = {
    "primes_acquises_tnd", "cout_sinistres_tnd",
    "nb_sinistres", "ratio_combine_pct"
}

# Valeurs plancher réalistes pour éviter prédictions aberrantes
FLOOR_VALUES = {
    "primes_acquises_tnd": 100_000,
    "cout_sinistres_tnd":  50_000,
    "nb_sinistres":        10,
    "ratio_combine_pct":   30.0,
}


def _clean(val):
    if isinstance(val, Decimal): return float(val)
    return float(val) if val else 0.0


def _apply_floor(values: np.ndarray, indicateur: str) -> np.ndarray:
    """Applique un plancher réaliste selon l'indicateur."""
    floor = FLOOR_VALUES.get(indicateur, 0)
    return np.maximum(values, floor)


def _forecast_with_prophet(df: pd.DataFrame, nb_mois: int, indicateur: str):
    """Essaie Prophet avec paramètres adaptés à l'indicateur."""
    try:
        from prophet import Prophet
        import warnings
        warnings.filterwarnings("ignore")

        floor = FLOOR_VALUES.get(indicateur, 0)

        # Paramètres adaptés selon l'indicateur
        if indicateur == "ratio_combine_pct":
            # Ratio : plus volatile, changepoints plus flexibles
            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
                seasonality_mode="additive",
                changepoint_prior_scale=0.3,
                seasonality_prior_scale=10,
            )
        elif indicateur in ("cout_sinistres_tnd", "nb_sinistres"):
            # Coût/sinistres : saisonnalité forte
            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
                seasonality_mode="multiplicative",
                changepoint_prior_scale=0.1,
                seasonality_prior_scale=15,
            )
        else:
            # Primes : tendance haussière régulière
            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
                seasonality_mode="multiplicative",
                changepoint_prior_scale=0.05,
            )

        model.fit(df[["ds", "y"]])
        future = model.make_future_dataframe(periods=nb_mois, freq="MS")
        forecast = model.predict(future)

        # Appliquer plancher réaliste
        forecast["yhat"]       = _apply_floor(forecast["yhat"].values, indicateur)
        forecast["yhat_lower"] = _apply_floor(forecast["yhat_lower"].values, indicateur)
        forecast["yhat_upper"] = _apply_floor(forecast["yhat_upper"].values, indicateur)

        return forecast, "Prophet"

    except Exception as e:
        logger.warning(f"Prophet indisponible ({e}), essai SARIMA")
        return None, None


def _forecast_with_sarima(df: pd.DataFrame, nb_mois: int, indicateur: str):
    """SARIMA(1,1,1)(1,1,1)[12] — capte saisonnalité annuelle."""
    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        import warnings
        warnings.filterwarnings("ignore")

        y = df["y"].values
        model = SARIMAX(
            y,
            order=(1, 1, 1),
            seasonal_order=(1, 1, 1, 12),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        result = model.fit(disp=False, maxiter=200)

        forecast_obj = result.get_forecast(steps=nb_mois)
        yhat   = forecast_obj.predicted_mean
        ci     = forecast_obj.conf_int(alpha=0.05)
        lower  = ci.iloc[:, 0].values
        upper  = ci.iloc[:, 1].values

        last_date    = df["ds"].max()
        future_dates = pd.date_range(start=last_date + pd.DateOffset(months=1), periods=nb_mois, freq="MS")

        # Historique prédit (in-sample)
        hist_pred = result.fittedvalues

        all_ds    = pd.concat([df["ds"], pd.Series(future_dates)], ignore_index=True)
        all_yhat  = np.concatenate([hist_pred, yhat])
        all_lower = np.concatenate([hist_pred - 1.96 * np.std(hist_pred - y), lower])
        all_upper = np.concatenate([hist_pred + 1.96 * np.std(hist_pred - y), upper])

        fc = pd.DataFrame({
            "ds":         all_ds,
            "yhat":       _apply_floor(all_yhat, indicateur),
            "yhat_lower": _apply_floor(all_lower, indicateur),
            "yhat_upper": _apply_floor(all_upper, indicateur),
        })
        return fc, "SARIMA(1,1,1)(1,1,1)[12]"

    except Exception as e:
        logger.warning(f"SARIMA indisponible ({e}), essai Holt-Winters")
        return None, None


def _forecast_with_holtwinters(df: pd.DataFrame, nb_mois: int, indicateur: str):
    """Holt-Winters (lissage exponentiel triple) avec saisonnalité annuelle."""
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        import warnings
        warnings.filterwarnings("ignore")

        y = df["y"].values
        n = len(y)

        # Besoin d'au moins 2 cycles saisonniers (24 mois)
        if n < 24:
            raise ValueError("Données insuffisantes pour Holt-Winters (min 24 mois)")

        model = ExponentialSmoothing(
            y,
            seasonal_periods=12,
            trend="add",
            seasonal="add",
            damped_trend=True,
        )
        result = model.fit(optimized=True)

        yhat_future = result.forecast(nb_mois)
        yhat_hist   = result.fittedvalues
        std         = np.std(result.resid)

        last_date    = df["ds"].max()
        future_dates = pd.date_range(start=last_date + pd.DateOffset(months=1), periods=nb_mois, freq="MS")

        all_ds    = pd.concat([df["ds"], pd.Series(future_dates)], ignore_index=True)
        all_yhat  = np.concatenate([yhat_hist, yhat_future])
        all_lower = all_yhat - 1.96 * std
        all_upper = all_yhat + 1.96 * std

        fc = pd.DataFrame({
            "ds":         all_ds,
            "yhat":       _apply_floor(all_yhat, indicateur),
            "yhat_lower": _apply_floor(all_lower, indicateur),
            "yhat_upper": _apply_floor(all_upper, indicateur),
        })
        return fc, "Holt-Winters (lissage exponentiel)"

    except Exception as e:
        logger.warning(f"Holt-Winters indisponible ({e}), fallback régression poly")
        return None, None


def _forecast_poly_seasonal(df: pd.DataFrame, nb_mois: int, indicateur: str):
    """
    Fallback final : régression polynomiale degré 2 + saisonnalité mensuelle sin/cos.
    Toujours disponible, sans dépendances externes.
    """
    from sklearn.linear_model import Ridge
    import warnings
    warnings.filterwarnings("ignore")

    df = df.copy()
    n  = len(df)
    df["t"]     = np.arange(n)
    df["t2"]    = df["t"] ** 2
    df["mois"]  = df["ds"].dt.month

    # Saisonnalité complète (6 harmoniques)
    for k in range(1, 4):
        df[f"sin_{k}"] = np.sin(2 * np.pi * k * df["mois"] / 12)
        df[f"cos_{k}"] = np.cos(2 * np.pi * k * df["mois"] / 12)

    features = ["t", "t2"] + [f"sin_{k}" for k in range(1,4)] + [f"cos_{k}" for k in range(1,4)]
    X = df[features].values
    y = df["y"].values

    reg = Ridge(alpha=1.0).fit(X, y)
    std = np.std(reg.predict(X) - y)

    last_date    = df["ds"].max()
    future_dates = pd.date_range(start=last_date + pd.DateOffset(months=1), periods=nb_mois, freq="MS")

    t_fut  = np.arange(n, n + nb_mois)
    t2_fut = t_fut ** 2
    m_fut  = future_dates.month

    X_fut_rows = [t_fut, t2_fut]
    for k in range(1, 4):
        X_fut_rows.append(np.sin(2 * np.pi * k * m_fut / 12))
        X_fut_rows.append(np.cos(2 * np.pi * k * m_fut / 12))
    X_future = np.column_stack(X_fut_rows)

    # Reconstruire dans le bon ordre de features
    X_future_df = pd.DataFrame({
        "t": t_fut, "t2": t2_fut,
        **{f"sin_{k}": np.sin(2 * np.pi * k * m_fut / 12) for k in range(1,4)},
        **{f"cos_{k}": np.cos(2 * np.pi * k * m_fut / 12) for k in range(1,4)},
    })
    yhat_future = reg.predict(X_future_df[features].values)
    yhat_hist   = reg.predict(X)

    all_ds    = pd.concat([df["ds"], pd.Series(future_dates)], ignore_index=True)
    all_yhat  = np.concatenate([yhat_hist, yhat_future])
    all_lower = all_yhat - 1.96 * std
    all_upper = all_yhat + 1.96 * std

    fc = pd.DataFrame({
        "ds":         all_ds,
        "yhat":       _apply_floor(all_yhat, indicateur),
        "yhat_lower": _apply_floor(all_lower, indicateur),
        "yhat_upper": _apply_floor(all_upper, indicateur),
    })
    return fc, "Régression poly+saisonnalité"


def _run_forecast(df: pd.DataFrame, nb_mois: int, indicateur: str):
    """
    Cascade de méthodes :
    1. Prophet
    2. SARIMA
    3. Holt-Winters
    4. Régression poly+saisonnalité (toujours disponible)
    """
    for fn in [_forecast_with_prophet, _forecast_with_sarima, _forecast_with_holtwinters]:
        fc, methode = fn(df, nb_mois, indicateur)
        if fc is not None:
            return fc, methode

    return _forecast_poly_seasonal(df, nb_mois, indicateur)


def get_forecast(
    departement: str = "Automobile",
    indicateur: str = "primes_acquises_tnd",
    nb_mois: int = 6,
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

    if len(rows) < 12:
        return {"error": "Données insuffisantes pour la prévision (minimum 12 mois requis)"}

    df      = pd.DataFrame(rows, columns=["annee", "mois", "y"])
    df["ds"] = pd.to_datetime(df.apply(lambda r: f"{int(r.annee)}-{int(r.mois):02d}-01", axis=1))
    df["y"]  = df["y"].apply(_clean)

    forecast, methode = _run_forecast(df, nb_mois, indicateur)

    historique = [
        {"periode": row.ds.strftime("%Y-%m"), "valeur": round(float(row.y), 2), "type": "reel"}
        for _, row in df.iterrows()
    ]

    ds_max      = df["ds"].max()
    future_rows = forecast[forecast["ds"] > ds_max]

    previsions = [
        {
            "periode":    row.ds.strftime("%Y-%m"),
            "valeur":     round(float(row.yhat), 2),
            "valeur_min": round(float(row.yhat_lower), 2),
            "valeur_max": round(float(row.yhat_upper), 2),
            "type":       "prevision",
        }
        for _, row in future_rows.iterrows()
    ]

    dernier_reel  = float(df["y"].iloc[-1])
    premiere_prev = previsions[0]["valeur"] if previsions else dernier_reel
    tendance      = "hausse" if premiere_prev > dernier_reel * 1.02 else \
                    "baisse" if premiere_prev < dernier_reel * 0.98 else "stable"
    variation_pct = round((premiere_prev - dernier_reel) / dernier_reel * 100, 1) if dernier_reel else 0

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