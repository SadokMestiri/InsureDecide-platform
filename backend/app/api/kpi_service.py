"""
Service KPI — Logique métier pour les requêtes analytiques
Toutes les requêtes SQL sont optimisées pour la table kpis_mensuels
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime

from app.schemas.kpi import (
    KPISummary, KPIDepartement, EvolutionPoint,
    EvolutionResponse, ComparaisonPoint, Alerte
)

DEPARTEMENTS = ["Automobile", "Vie", "Immobilier"]

# ── Seuils d'alerte métier
SEUILS = {
    "ratio_combine_critique": 110.0,
    "ratio_combine_warning": 95.0,
    "taux_resiliation_critique": 15.0,
    "taux_resiliation_warning": 10.0,
    "frequence_sinistres_critique": 25.0,
    "nb_fraudes_warning": 5,
}


def get_derniere_periode(db: Session) -> dict:
    """Retourne la dernière année/mois disponibles dans les KPIs."""
    row = db.execute(text("""
        SELECT annee, mois, periode
        FROM kpis_mensuels
        ORDER BY annee DESC, mois DESC
        LIMIT 1
    """)).fetchone()
    return {"annee": row.annee, "mois": row.mois, "periode": row.periode} if row else {}


def get_summary(db: Session, annee: Optional[int] = None, mois: Optional[int] = None) -> KPISummary:
    """KPIs globaux consolidés sur tous les départements pour une période."""
    periode = get_derniere_periode(db) if not annee else {"annee": annee, "mois": mois}

    row = db.execute(text("""
        SELECT
            SUM(nb_contrats_actifs)         AS total_contrats,
            SUM(primes_acquises_tnd)         AS total_primes,
            SUM(nb_sinistres)                AS total_sinistres,
            SUM(cout_sinistres_tnd)          AS total_cout,
            AVG(ratio_combine_pct)           AS ratio_moyen,
            AVG(taux_resiliation_pct)        AS resiliation_moyenne,
            SUM(provision_totale_tnd)        AS total_provisions,
            SUM(nb_suspicions_fraude)        AS total_fraudes,
            MAX(periode)                     AS periode_label
        FROM kpis_mensuels
        WHERE annee = :annee AND mois = :mois
    """), {"annee": periode["annee"], "mois": periode["mois"]}).fetchone()

    return KPISummary(
        total_contrats_actifs=int(row.total_contrats or 0),
        total_primes_tnd=round(float(row.total_primes or 0), 2),
        total_sinistres=int(row.total_sinistres or 0),
        total_cout_sinistres_tnd=round(float(row.total_cout or 0), 2),
        ratio_combine_moyen_pct=round(float(row.ratio_moyen or 0), 2),
        taux_resiliation_moyen_pct=round(float(row.resiliation_moyenne or 0), 2),
        total_provisions_tnd=round(float(row.total_provisions or 0), 2),
        total_suspicions_fraude=int(row.total_fraudes or 0),
        periode_label=str(row.periode_label or ""),
    )


def get_kpis_par_departement(
    db: Session, annee: Optional[int] = None, mois: Optional[int] = None
) -> List[KPIDepartement]:
    """KPIs détaillés par département pour la période demandée + tendance vs mois précédent."""
    periode = get_derniere_periode(db) if not annee else {"annee": annee, "mois": mois}

    rows = db.execute(text("""
        SELECT
            k.departement, k.periode, k.nb_contrats_actifs,
            k.primes_acquises_tnd, k.cout_sinistres_tnd, k.nb_sinistres,
            k.frequence_sinistres_pct, k.cout_moyen_sinistre_tnd,
            k.ratio_combine_pct, k.taux_resiliation_pct,
            k.provision_totale_tnd, k.nb_suspicions_fraude,
            prev.ratio_combine_pct AS ratio_precedent
        FROM kpis_mensuels k
        LEFT JOIN kpis_mensuels prev
            ON prev.departement = k.departement
            AND (
                (k.mois > 1 AND prev.annee = k.annee AND prev.mois = k.mois - 1)
                OR
                (k.mois = 1 AND prev.annee = k.annee - 1 AND prev.mois = 12)
            )
        WHERE k.annee = :annee AND k.mois = :mois
        ORDER BY k.departement
    """), {"annee": periode["annee"], "mois": periode["mois"]}).fetchall()

    result = []
    for r in rows:
        # Calcul tendance ratio combiné
        tendance = "stable"
        variation = 0.0
        if r.ratio_precedent is not None:
            variation = round(float(r.ratio_combine_pct) - float(r.ratio_precedent), 2)
            if variation > 2:
                tendance = "hausse"
            elif variation < -2:
                tendance = "baisse"

        result.append(KPIDepartement(
            departement=r.departement,
            periode=r.periode,
            nb_contrats_actifs=int(r.nb_contrats_actifs),
            primes_acquises_tnd=round(float(r.primes_acquises_tnd), 2),
            cout_sinistres_tnd=round(float(r.cout_sinistres_tnd), 2),
            nb_sinistres=int(r.nb_sinistres),
            frequence_sinistres_pct=round(float(r.frequence_sinistres_pct), 2),
            cout_moyen_sinistre_tnd=round(float(r.cout_moyen_sinistre_tnd), 2),
            ratio_combine_pct=round(float(r.ratio_combine_pct), 2),
            taux_resiliation_pct=round(float(r.taux_resiliation_pct), 2),
            provision_totale_tnd=round(float(r.provision_totale_tnd), 2),
            nb_suspicions_fraude=int(r.nb_suspicions_fraude),
            tendance_ratio=tendance,
            variation_ratio_pct=variation,
        ))
    return result


def get_evolution(
    db: Session,
    indicateur: str = "ratio_combine_pct",
    departement: Optional[str] = None,
    annee_debut: int = 2020,
    annee_fin: int = 2024,
    nb_mois: Optional[int] = None,
) -> EvolutionResponse:
    """Série temporelle d'un indicateur pour les graphiques courbes."""

    # Colonnes autorisées (sécurité SQL injection)
    colonnes_valides = {
        "ratio_combine_pct": ("Ratio Combiné", "%"),
        "primes_acquises_tnd": ("Primes Acquises", "TND"),
        "cout_sinistres_tnd": ("Coût Sinistres", "TND"),
        "nb_sinistres": ("Nombre de Sinistres", "unités"),
        "frequence_sinistres_pct": ("Fréquence Sinistres", "%"),
        "taux_resiliation_pct": ("Taux de Résiliation", "%"),
        "provision_totale_tnd": ("Provisions Totales", "TND"),
        "nb_suspicions_fraude": ("Suspicions de Fraude", "unités"),
        "cout_moyen_sinistre_tnd": ("Coût Moyen Sinistre", "TND"),
    }

    if indicateur not in colonnes_valides:
        indicateur = "ratio_combine_pct"

    label, unite = colonnes_valides[indicateur]

    # Filtre sur derniers N mois si demandé
    extra_filter = ""
    if nb_mois:
        extra_filter = f"AND (annee * 12 + mois) >= (SELECT MAX(annee)*12+mois - {nb_mois} FROM kpis_mensuels)"

    dept_filter = "AND departement = :departement" if departement else ""

    sql = f"""
        SELECT departement, annee, mois, periode,
               CAST({indicateur} AS FLOAT) AS valeur
        FROM kpis_mensuels
        WHERE annee BETWEEN :annee_debut AND :annee_fin
        {dept_filter}
        {extra_filter}
        ORDER BY departement, annee, mois
    """

    params = {"annee_debut": annee_debut, "annee_fin": annee_fin}
    if departement:
        params["departement"] = departement

    rows = db.execute(text(sql), params).fetchall()

    series = [
        EvolutionPoint(
            periode=r.periode,
            annee=r.annee,
            mois=r.mois,
            valeur=round(float(r.valeur), 2),
            departement=r.departement,
        )
        for r in rows
    ]

    depts = list({r.departement for r in rows})

    return EvolutionResponse(
        indicateur=label,
        unite=unite,
        departements=sorted(depts),
        series=series,
    )


def get_comparaison(
    db: Session, annee: Optional[int] = None, mois: Optional[int] = None
) -> List[ComparaisonPoint]:
    """Données de comparaison entre départements pour les barres."""
    periode = get_derniere_periode(db) if not annee else {"annee": annee, "mois": mois}

    rows = db.execute(text("""
        SELECT departement, primes_acquises_tnd, cout_sinistres_tnd,
               frais_gestion_tnd, ratio_combine_pct, taux_resiliation_pct,
               nb_sinistres, nb_contrats_actifs
        FROM kpis_mensuels
        WHERE annee = :annee AND mois = :mois
        ORDER BY departement
    """), {"annee": periode["annee"], "mois": periode["mois"]}).fetchall()

    return [
        ComparaisonPoint(
            departement=r.departement,
            primes_acquises_tnd=round(float(r.primes_acquises_tnd), 2),
            cout_sinistres_tnd=round(float(r.cout_sinistres_tnd), 2),
            frais_gestion_tnd=round(float(r.frais_gestion_tnd), 2),
            ratio_combine_pct=round(float(r.ratio_combine_pct), 2),
            taux_resiliation_pct=round(float(r.taux_resiliation_pct), 2),
            nb_sinistres=int(r.nb_sinistres),
            nb_contrats_actifs=int(r.nb_contrats_actifs),
        )
        for r in rows
    ]


def get_alertes(db: Session, nb_mois: int = 3) -> List[Alerte]:
    """Détecte automatiquement les anomalies sur les N derniers mois."""

    rows = db.execute(text("""
        SELECT departement, annee, mois, periode,
               ratio_combine_pct, taux_resiliation_pct,
               frequence_sinistres_pct, nb_suspicions_fraude,
               nb_sinistres
        FROM kpis_mensuels
        WHERE (annee * 12 + mois) >= (
            SELECT MAX(annee * 12 + mois) - :nb_mois FROM kpis_mensuels
        )
        ORDER BY annee DESC, mois DESC
    """), {"nb_mois": nb_mois}).fetchall()

    alertes = []
    alerte_id = 0

    for r in rows:
        dept = r.departement
        periode = r.periode

        # 1. Ratio combiné critique (> 110%)
        if float(r.ratio_combine_pct) > SEUILS["ratio_combine_critique"]:
            alertes.append(Alerte(
                id=f"alerte_{alerte_id}",
                departement=dept,
                type_alerte="ratio_eleve",
                severite="critique",
                message=f"Ratio combiné critique à {round(float(r.ratio_combine_pct), 1)}% — département déficitaire",
                valeur_actuelle=round(float(r.ratio_combine_pct), 2),
                seuil=SEUILS["ratio_combine_critique"],
                periode=periode,
                recommandation="Réviser la tarification et renforcer la sélection des risques.",
            ))
            alerte_id += 1

        # 2. Ratio combiné en zone d'alerte (95-110%)
        elif float(r.ratio_combine_pct) > SEUILS["ratio_combine_warning"]:
            alertes.append(Alerte(
                id=f"alerte_{alerte_id}",
                departement=dept,
                type_alerte="ratio_eleve",
                severite="warning",
                message=f"Ratio combiné à {round(float(r.ratio_combine_pct), 1)}% — approche du seuil critique",
                valeur_actuelle=round(float(r.ratio_combine_pct), 2),
                seuil=SEUILS["ratio_combine_warning"],
                periode=periode,
                recommandation="Surveiller l'évolution et préparer un plan d'action tarifaire.",
            ))
            alerte_id += 1

        # 3. Taux de résiliation élevé
        if float(r.taux_resiliation_pct) > SEUILS["taux_resiliation_critique"]:
            alertes.append(Alerte(
                id=f"alerte_{alerte_id}",
                departement=dept,
                type_alerte="resiliation",
                severite="critique",
                message=f"Taux de résiliation à {round(float(r.taux_resiliation_pct), 1)}% — rétention clients critique",
                valeur_actuelle=round(float(r.taux_resiliation_pct), 2),
                seuil=SEUILS["taux_resiliation_critique"],
                periode=periode,
                recommandation="Lancer une campagne de fidélisation et analyser les motifs de résiliation.",
            ))
            alerte_id += 1

        # 4. Suspicions de fraude élevées
        if int(r.nb_suspicions_fraude) >= SEUILS["nb_fraudes_warning"]:
            alertes.append(Alerte(
                id=f"alerte_{alerte_id}",
                departement=dept,
                type_alerte="fraude",
                severite="warning",
                message=f"{int(r.nb_suspicions_fraude)} suspicions de fraude détectées",
                valeur_actuelle=float(r.nb_suspicions_fraude),
                seuil=float(SEUILS["nb_fraudes_warning"]),
                periode=periode,
                recommandation="Déclencher une investigation approfondie sur les dossiers suspects.",
            ))
            alerte_id += 1

    # Trier par sévérité : critique en premier
    ordre = {"critique": 0, "warning": 1, "info": 2}
    alertes.sort(key=lambda a: ordre.get(a.severite, 3))

    return alertes[:20]  # Maximum 20 alertes
