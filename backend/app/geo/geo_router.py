"""
InsureDecide — Router Géographique

Routes :
  GET /api/geo/sinistres          → stats sinistres par gouvernorat
  GET /api/geo/sinistres/top      → top N gouvernorats
  GET /api/geo/gouvernorat/{name} → détail d'un gouvernorat
"""

import asyncio
from typing import Optional
from fastapi import Query
import logging
from typing import Optional
from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Géographie"])


@router.get("/api/geo/sinistres")
async def geo_sinistres(departement: Optional[str] = Query(None)):
    loop = asyncio.get_event_loop()
    from app.geo.geo_service import get_sinistres_par_gouvernorat
    data = await loop.run_in_executor(None, get_sinistres_par_gouvernorat, departement)
    return {"gouvernorats": data, "total": len(data)}


@router.get("/api/geo/sinistres/top")
async def geo_top(
    departement: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=24),
):
    loop = asyncio.get_event_loop()
    from app.geo.geo_service import get_top_gouvernorats
    data = await loop.run_in_executor(None, get_top_gouvernorats, departement, limit)
    return {"top": data}


@router.get("/api/geo/gouvernorat/{gouvernorat}")
async def geo_detail(gouvernorat: str):
    loop = asyncio.get_event_loop()
    from app.geo.geo_service import get_gouvernorat_detail
    data = await loop.run_in_executor(None, get_gouvernorat_detail, gouvernorat)
    return data


# ── Clients à risque
from fastapi import Body

@router.get("/api/risque/clients")
async def clients_risque(
    departement:      Optional[str] = Query(None),
    gouvernorat:      Optional[str] = Query(None),
    seuil_sinistres:  int           = Query(2, ge=1),
    limit:            int           = Query(50, ge=1, le=200),
    offset:           int           = Query(0, ge=0),
):
    loop = asyncio.get_event_loop()
    from app.geo.risque_service import get_clients_risque
    return await loop.run_in_executor(
        None, get_clients_risque, departement, gouvernorat, seuil_sinistres, limit, offset
    )


@router.get("/api/risque/client/{client_id}")
async def client_detail(client_id: str):
    loop = asyncio.get_event_loop()
    from app.geo.risque_service import get_client_detail
    return await loop.run_in_executor(None, get_client_detail, client_id)
