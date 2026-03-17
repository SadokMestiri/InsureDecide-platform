"""
Router KPI — Toutes les routes /api/kpis et /api/dashboard
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.schemas.kpi import (
    KPISummary, KPIDepartement, EvolutionResponse,
    ComparaisonPoint, Alerte, DashboardResponse
)
from app.api import kpi_service

router = APIRouter(prefix="/api", tags=["KPIs & Dashboard"])

DEPARTEMENTS_VALIDES = ["Automobile", "Vie", "Immobilier"]


# ──────────────────────────────────────────────────────────
# 1. RÉSUMÉ GLOBAL
# ──────────────────────────────────────────────────────────
@router.get(
    "/kpis/summary",
    response_model=KPISummary,
    summary="KPIs globaux consolidés",
    description="Retourne les KPIs agrégés sur tous les départements pour la période demandée."
)
def kpis_summary(
    annee: Optional[int] = Query(None, description="Année (défaut: dernière disponible)"),
    mois: Optional[int] = Query(None, ge=1, le=12, description="Mois 1-12 (défaut: dernier disponible)"),
    db: Session = Depends(get_db)
):
    return kpi_service.get_summary(db, annee, mois)


# ──────────────────────────────────────────────────────────
# 2. KPIs PAR DÉPARTEMENT
# ──────────────────────────────────────────────────────────
@router.get(
    "/kpis/departements",
    response_model=List[KPIDepartement],
    summary="KPIs par département",
    description="Retourne les KPIs détaillés pour chaque département avec tendance vs mois précédent."
)
def kpis_par_departement(
    annee: Optional[int] = Query(None),
    mois: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db)
):
    return kpi_service.get_kpis_par_departement(db, annee, mois)


@router.get(
    "/kpis/departements/{departement}",
    response_model=KPIDepartement,
    summary="KPIs d'un département spécifique"
)
def kpis_departement(
    departement: str,
    annee: Optional[int] = Query(None),
    mois: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db)
):
    if departement not in DEPARTEMENTS_VALIDES:
        raise HTTPException(
            status_code=400,
            detail=f"Département invalide. Valeurs acceptées : {DEPARTEMENTS_VALIDES}"
        )
    tous = kpi_service.get_kpis_par_departement(db, annee, mois)
    for k in tous:
        if k.departement == departement:
            return k
    raise HTTPException(status_code=404, detail=f"Aucune donnée pour {departement}")


# ──────────────────────────────────────────────────────────
# 3. ÉVOLUTION TEMPORELLE (graphiques courbes)
# ──────────────────────────────────────────────────────────
@router.get(
    "/kpis/evolution",
    response_model=EvolutionResponse,
    summary="Évolution temporelle d'un indicateur",
    description="""
Retourne la série temporelle d'un indicateur pour alimenter les graphiques courbes.

**Indicateurs disponibles :**
- `ratio_combine_pct` — Ratio combiné (%)
- `primes_acquises_tnd` — Primes acquises (TND)
- `cout_sinistres_tnd` — Coût des sinistres (TND)
- `nb_sinistres` — Nombre de sinistres
- `frequence_sinistres_pct` — Fréquence des sinistres (%)
- `taux_resiliation_pct` — Taux de résiliation (%)
- `provision_totale_tnd` — Provisions totales (TND)
- `nb_suspicions_fraude` — Suspicions de fraude
- `cout_moyen_sinistre_tnd` — Coût moyen par sinistre (TND)
    """
)
def kpis_evolution(
    indicateur: str = Query("ratio_combine_pct", description="Colonne à tracer"),
    departement: Optional[str] = Query(None, description="Filtrer sur un département"),
    annee_debut: int = Query(2020, ge=2020, le=2024),
    annee_fin: int = Query(2024, ge=2020, le=2024),
    nb_mois: Optional[int] = Query(None, description="Derniers N mois (priorité sur annee_debut/fin)"),
    db: Session = Depends(get_db)
):
    if departement and departement not in DEPARTEMENTS_VALIDES:
        raise HTTPException(status_code=400, detail=f"Département invalide : {departement}")
    return kpi_service.get_evolution(db, indicateur, departement, annee_debut, annee_fin, nb_mois)


# ──────────────────────────────────────────────────────────
# 4. COMPARAISON ENTRE DÉPARTEMENTS (graphiques barres)
# ──────────────────────────────────────────────────────────
@router.get(
    "/kpis/comparaison",
    response_model=List[ComparaisonPoint],
    summary="Comparaison entre départements",
    description="Données pour les graphiques en barres comparant les 3 départements sur une période."
)
def kpis_comparaison(
    annee: Optional[int] = Query(None),
    mois: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db)
):
    return kpi_service.get_comparaison(db, annee, mois)


# ──────────────────────────────────────────────────────────
# 5. ALERTES ANOMALIES
# ──────────────────────────────────────────────────────────
@router.get(
    "/dashboard/alertes",
    response_model=List[Alerte],
    summary="Alertes et anomalies détectées",
    description="""
Détecte automatiquement les anomalies sur les N derniers mois.

**Règles de détection :**
- Ratio combiné > 110% → Alerte critique
- Ratio combiné > 95% → Warning
- Taux résiliation > 15% → Alerte critique
- Suspicions fraude ≥ 5 → Warning
    """
)
def dashboard_alertes(
    nb_mois: int = Query(3, ge=1, le=12, description="Analyser les N derniers mois"),
    db: Session = Depends(get_db)
):
    return kpi_service.get_alertes(db, nb_mois)


# ──────────────────────────────────────────────────────────
# 6. DASHBOARD COMPLET (un seul appel)
# ──────────────────────────────────────────────────────────
@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Dashboard complet — un seul appel",
    description="Agrège summary + par département + alertes en un seul appel optimisé."
)
def dashboard_complet(
    annee: Optional[int] = Query(None),
    mois: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db)
):
    summary = kpi_service.get_summary(db, annee, mois)
    par_departement = kpi_service.get_kpis_par_departement(db, annee, mois)
    alertes = kpi_service.get_alertes(db)
    return DashboardResponse(
        summary=summary,
        par_departement=par_departement,
        alertes=alertes,
        derniere_mise_a_jour=datetime.now().isoformat(),
        source=summary.source,
    )


# ──────────────────────────────────────────────────────────
# 7. PÉRIODES DISPONIBLES (pour les selects du frontend)
# ──────────────────────────────────────────────────────────
@router.get(
    "/kpis/periodes",
    summary="Liste des périodes disponibles",
    description="Retourne toutes les périodes disponibles dans les données."
)
def periodes_disponibles(db: Session = Depends(get_db)):
    rows = db.execute(
        text("SELECT DISTINCT annee, mois, periode FROM kpis_mensuels ORDER BY annee DESC, mois DESC")
    ).fetchall()
    return [{"annee": r.annee, "mois": r.mois, "periode": r.periode} for r in rows]