"""
InsureDecide — Service Segmentation Clients
Clustering K-Means basé sur un profil client agrégé (contrats, primes, sinistres, fraude).
"""

import os
import logging
import psycopg2
import pandas as pd
import numpy as np
from decimal import Decimal
from typing import Optional
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://insuredecide_user:insuredecide_pass@postgres:5432/insuredecide"
)


def _clean(val):
    if isinstance(val, Decimal):
        return float(val)
    return float(val) if val is not None else 0.0


def _label_segment(avg_prime: float, avg_sinistre: float, avg_fraude: float, rank_prime: int) -> str:
    if rank_prime == 1 and avg_fraude < 0.2:
        return "VIP rentable"
    if avg_prime >= 2000 and avg_sinistre < 1200:
        return "Premium stable"
    if avg_fraude >= 0.5 or avg_sinistre >= 1800:
        return "A risque"
    return "Standard"


def get_client_segmentation(
    n_clusters: int = 4,
    limit_clients: int = 20000,
    departement: Optional[str] = None,
) -> dict:
    n_clusters = max(2, min(8, int(n_clusters)))
    limit_clients = max(1000, min(60000, int(limit_clients)))

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute(
        """
        WITH contrats AS (
            SELECT client_id, prime_annuelle_tnd, statut, date_debut, 'Automobile' AS departement
            FROM contrats_automobile
            UNION ALL
            SELECT client_id, prime_annuelle_tnd, statut, date_debut, 'Vie' AS departement
            FROM contrats_vie
            UNION ALL
            SELECT client_id, prime_annuelle_tnd, statut, date_debut, 'Immobilier' AS departement
            FROM contrats_immobilier
        ),
        contrats_filtre AS (
            SELECT *
            FROM contrats
            WHERE (%s IS NULL OR departement = %s)
        ),
        contrats_agg AS (
            SELECT
                client_id,
                COUNT(*) AS nb_contrats,
                SUM(COALESCE(prime_annuelle_tnd, 0)) AS total_prime_annuelle,
                SUM(CASE WHEN statut IN ('Actif') THEN 1 ELSE 0 END) AS nb_contrats_actifs,
                SUM(CASE WHEN statut IN ('Résilié', 'Racheté', 'Échu') THEN 1 ELSE 0 END) AS nb_contrats_resilies,
                MAX(date_debut) AS derniere_souscription
            FROM contrats_filtre
            GROUP BY client_id
        ),
        sinistres_agg AS (
            SELECT
                client_id,
                COUNT(*) AS nb_sinistres,
                SUM(COALESCE(cout_sinistre_tnd, 0)) AS total_cout_sinistres,
                AVG(COALESCE(cout_sinistre_tnd, 0)) AS cout_moyen_sinistre,
                SUM(CASE WHEN COALESCE(CAST(suspicion_fraude AS INTEGER), 0) = 1 THEN 1 ELSE 0 END) AS nb_fraudes,
                AVG(COALESCE(delai_reglement_jours, 0)) AS delai_reglement_moyen
            FROM sinistres
            WHERE (%s IS NULL OR departement = %s)
            GROUP BY client_id
        )
        SELECT
            c.client_id,
            COALESCE(c.age, 0) AS age,
            COALESCE(c.revenu_mensuel_tnd, 0) AS revenu_mensuel_tnd,
            COALESCE(ca.nb_contrats, 0) AS nb_contrats,
            COALESCE(ca.total_prime_annuelle, 0) AS total_prime_annuelle,
            COALESCE(ca.nb_contrats_actifs, 0) AS nb_contrats_actifs,
            COALESCE(ca.nb_contrats_resilies, 0) AS nb_contrats_resilies,
            COALESCE(sa.nb_sinistres, 0) AS nb_sinistres,
            COALESCE(sa.total_cout_sinistres, 0) AS total_cout_sinistres,
            COALESCE(sa.cout_moyen_sinistre, 0) AS cout_moyen_sinistre,
            COALESCE(sa.nb_fraudes, 0) AS nb_fraudes,
            COALESCE(sa.delai_reglement_moyen, 0) AS delai_reglement_moyen
        FROM contrats_agg ca
        JOIN clients c ON c.client_id = ca.client_id
        LEFT JOIN sinistres_agg sa ON c.client_id = sa.client_id
        ORDER BY c.client_id
        LIMIT %s
        """,
        [departement, departement, departement, departement, limit_clients],
    )

    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    cur.close()
    conn.close()

    if not rows:
        return {"status": "error", "detail": "Aucune donnée client disponible"}

    df = pd.DataFrame(rows, columns=cols)
    for c in cols[1:]:
        df[c] = df[c].apply(_clean)

    df["frequence_sinistre"] = np.where(df["nb_contrats"] > 0, df["nb_sinistres"] / df["nb_contrats"], 0.0)
    df["fraude_rate"] = np.where(df["nb_sinistres"] > 0, df["nb_fraudes"] / df["nb_sinistres"], 0.0)
    df["resiliation_rate"] = np.where(df["nb_contrats"] > 0, df["nb_contrats_resilies"] / df["nb_contrats"], 0.0)

    features = [
        "age",
        "revenu_mensuel_tnd",
        "nb_contrats",
        "total_prime_annuelle",
        "nb_contrats_actifs",
        "nb_sinistres",
        "total_cout_sinistres",
        "cout_moyen_sinistre",
        "frequence_sinistre",
        "fraude_rate",
        "resiliation_rate",
        "delai_reglement_moyen",
    ]

    df[features] = df[features].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    X = df[features].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    clusters = model.fit_predict(X_scaled)
    df["cluster"] = clusters

    sil = None
    if len(df) > n_clusters:
        try:
            sil = float(round(silhouette_score(X_scaled, clusters), 4))
        except Exception:
            sil = None

    profiles = (
        df.groupby("cluster", as_index=False)
        .agg(
            nb_clients=("client_id", "count"),
            avg_revenu=("revenu_mensuel_tnd", "mean"),
            avg_prime=("total_prime_annuelle", "mean"),
            avg_sinistre=("total_cout_sinistres", "mean"),
            avg_fraude_rate=("fraude_rate", "mean"),
            avg_resiliation_rate=("resiliation_rate", "mean"),
        )
        .sort_values("avg_prime", ascending=False)
        .reset_index(drop=True)
    )

    profiles["rank_prime"] = np.arange(1, len(profiles) + 1)
    profiles["segment_label"] = profiles.apply(
        lambda r: _label_segment(
            float(r["avg_prime"]),
            float(r["avg_sinistre"]),
            float(r["avg_fraude_rate"]),
            int(r["rank_prime"]),
        ),
        axis=1,
    )

    label_map = {
        int(r.cluster): r.segment_label
        for _, r in profiles.iterrows()
    }
    df["segment_label"] = df["cluster"].map(label_map)

    cluster_stats = []
    for _, r in profiles.iterrows():
        cluster_stats.append({
            "cluster": int(r["cluster"]),
            "segment_label": r["segment_label"],
            "nb_clients": int(r["nb_clients"]),
            "avg_revenu_mensuel_tnd": round(float(r["avg_revenu"]), 2),
            "avg_prime_annuelle_tnd": round(float(r["avg_prime"]), 2),
            "avg_cout_sinistres_tnd": round(float(r["avg_sinistre"]), 2),
            "avg_fraude_rate": round(float(r["avg_fraude_rate"]), 3),
            "avg_resiliation_rate": round(float(r["avg_resiliation_rate"]), 3),
        })

    top_clients = (
        df.sort_values(["total_prime_annuelle", "nb_contrats_actifs"], ascending=[False, False])
        .head(20)
    )
    top_clients_payload = [
        {
            "client_id": r["client_id"],
            "cluster": int(r["cluster"]),
            "segment_label": r["segment_label"],
            "total_prime_annuelle_tnd": round(float(r["total_prime_annuelle"]), 2),
            "nb_contrats": int(r["nb_contrats"]),
            "nb_sinistres": int(r["nb_sinistres"]),
            "fraude_rate": round(float(r["fraude_rate"]), 3),
        }
        for _, r in top_clients.iterrows()
    ]

    return {
        "status": "success",
        "algorithm": "kmeans",
        "departement": departement or "Tous",
        "n_clusters": n_clusters,
        "nb_clients": int(len(df)),
        "silhouette_score": sil,
        "features": features,
        "clusters": cluster_stats,
        "top_clients": top_clients_payload,
    }
