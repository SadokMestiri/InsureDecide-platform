"""
InsureDecide — Router FastAPI Denodo
Routes : /api/denodo/*
Fallback automatique vers PostgreSQL si Denodo indisponible
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.denodo_client import (
    is_denodo_available,
    get_kpis_enrichis,
    get_client_360,
    get_sinistres_enrichis,
    get_geo_resume,
    get_contrats_unifies,
)

router = APIRouter()


@router.get("/status")
def denodo_status():
    """Vérifie si Denodo est disponible."""
    available = is_denodo_available()
    return {
        "denodo_available": available,
        "source":           "denodo" if available else "postgresql_direct",
        "message":          "Denodo Platform 9.0 connecté" if available
                            else "Fallback PostgreSQL actif — Denodo indisponible",
    }


@router.get("/kpis/enrichis")
def kpis_enrichis(
    departement: Optional[str] = Query(None, description="Automobile | Vie | Immobilier")
):
    """KPIs mensuels enrichis avec alertes (ratio_combine, loss_ratio)."""
    try:
        return get_kpis_enrichis(departement)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clients/{client_id}/360")
def client_360(client_id: str):
    """Vue Client 360 : contrats + sinistres + interactions agent."""
    try:
        result = get_client_360(client_id)
        if not result.get("data"):
            raise HTTPException(status_code=404, detail=f"Client {client_id} non trouvé")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sinistres/enrichis")
def sinistres_enrichis(
    gouvernorat: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Sinistres avec contexte client (nom, âge, gouvernorat)."""
    try:
        return get_sinistres_enrichis(gouvernorat, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/geo/resume")
def geo_resume():
    """Résumé géographique : sinistres et coûts par gouvernorat."""
    try:
        return get_geo_resume()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contrats/unifies")
def contrats_unifies(
    client_id: Optional[int] = Query(None, description="Filtrer par client")
):
    """Contrats unifiés des 3 départements."""
    try:
        return get_contrats_unifies(client_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))