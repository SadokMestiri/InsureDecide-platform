"""
InsureDecide — Router WebSocket & Événements

Routes :
  WS  /ws/dashboard          → flux KPIs temps réel
  WS  /ws/alertes            → flux alertes temps réel
  GET /api/events/feed        → fil d'événements
  GET /api/events/refresh     → forcer la détection
  GET /api/events/stats       → statistiques du feed
  GET /api/ws/stats           → nb connexions WebSocket actives
"""

import logging
import asyncio
import json
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse

from app.events.ws_manager import manager
from app.events.events_service import get_feed, refresh_events, detect_events_from_kpis
from app.api.kpi_service import get_summary, get_kpis_par_departement, get_alertes

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Temps Réel"])


# ══════════════════════════════════════════════════
# WebSocket — Dashboard KPIs temps réel
# ══════════════════════════════════════════════════
@router.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket):
    """
    Connexion WebSocket pour le dashboard.
    Envoie les KPIs toutes les 30 secondes automatiquement.
    """
    await manager.connect(websocket, "dashboard")
    try:
        # Envoyer les données immédiatement à la connexion
        await _send_dashboard_data(websocket)

        # Boucle : écouter les messages client + envoyer mises à jour
        while True:
            try:
                # Attendre un message du client (ping ou commande)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg  = json.loads(data)

                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif msg.get("type") == "refresh":
                    await _send_dashboard_data(websocket)

            except asyncio.TimeoutError:
                # Timeout 30s → envoyer une mise à jour automatique
                await _send_dashboard_data(websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket, "dashboard")
    except Exception as e:
        logger.error(f"WebSocket dashboard erreur: {e}")
        manager.disconnect(websocket, "dashboard")


# ══════════════════════════════════════════════════
# WebSocket — Alertes temps réel
# ══════════════════════════════════════════════════
@router.websocket("/ws/alertes")
async def ws_alertes(websocket: WebSocket):
    """
    Connexion WebSocket pour les alertes.
    Envoie les nouvelles alertes dès qu'elles sont détectées.
    """
    await manager.connect(websocket, "alertes")
    try:
        await _send_alertes_data(websocket)
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                msg  = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                await _send_alertes_data(websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket, "alertes")
    except Exception as e:
        logger.error(f"WebSocket alertes erreur: {e}")
        manager.disconnect(websocket, "alertes")


# ══════════════════════════════════════════════════
# Helper : envoyer données dashboard
# ══════════════════════════════════════════════════
async def _send_dashboard_data(websocket: WebSocket):
    """Prépare et envoie le payload KPIs complet."""
    try:
        loop = asyncio.get_event_loop()
        summary   = await loop.run_in_executor(None, get_summary)
        depts     = await loop.run_in_executor(None, get_kpis_par_departement)

        payload = {
            "type":      "kpi_update",
            "summary":   summary.model_dump() if hasattr(summary, "model_dump") else summary,
            "departements": [d.model_dump() if hasattr(d, "model_dump") else d for d in depts],
            "timestamp": asyncio.get_event_loop().time(),
        }
        await websocket.send_text(json.dumps(payload, default=str))
    except Exception as e:
        logger.error(f"Erreur envoi dashboard: {e}")


async def _send_alertes_data(websocket: WebSocket):
    """Prépare et envoie le payload alertes."""
    try:
        loop    = asyncio.get_event_loop()
        alertes = await loop.run_in_executor(None, get_alertes, 3)
        payload = {
            "type":      "alertes_update",
            "alertes":   [a.model_dump() if hasattr(a, "model_dump") else a for a in alertes],
            "count":     len(alertes),
            "critiques": sum(1 for a in alertes if (a.severite if hasattr(a, "severite") else a.get("severite")) == "critique"),
            "timestamp": asyncio.get_event_loop().time(),
        }
        await websocket.send_text(json.dumps(payload, default=str))
    except Exception as e:
        logger.error(f"Erreur envoi alertes: {e}")


# ══════════════════════════════════════════════════
# GET /api/events/feed
# ══════════════════════════════════════════════════
@router.get("/api/events/feed")
def events_feed(
    limit:       int           = Query(20, ge=1, le=100),
    departement: Optional[str] = Query(None),
    severite:    Optional[str] = Query(None),
):
    """Fil d'événements métier détectés automatiquement."""
    events = get_feed(limit=limit, departement=departement, severite=severite)
    return {
        "events": events,
        "total":  len(events),
        "filtres": { "departement": departement, "severite": severite },
    }


# ══════════════════════════════════════════════════
# POST /api/events/refresh
# ══════════════════════════════════════════════════
@router.post("/api/events/refresh")
async def events_refresh():
    """Force la détection et sauvegarde des événements."""
    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, refresh_events)

    # Broadcaster les nouvelles alertes à tous les clients WS connectés
    events = get_feed(limit=10, severite="critique")
    if events and manager.connection_count("alertes") > 0:
        await manager.broadcast("alertes", {
            "type":   "alertes_update",
            "alertes": events,
            "count":  len(events),
        })

    return { "status": "success", **result }


# ══════════════════════════════════════════════════
# GET /api/events/stats
# ══════════════════════════════════════════════════
@router.get("/api/events/stats")
def events_stats():
    """Statistiques du fil d'événements."""
    all_events = get_feed(limit=100)
    by_sev  = {}
    by_dept = {}
    by_type = {}
    for e in all_events:
        sev  = e.get("severite", "info")
        dept = e.get("departement", "?")
        typ  = e.get("type", "?")
        by_sev[sev]   = by_sev.get(sev, 0)   + 1
        by_dept[dept] = by_dept.get(dept, 0)  + 1
        by_type[typ]  = by_type.get(typ, 0)   + 1
    return {
        "total":          len(all_events),
        "par_severite":   by_sev,
        "par_departement":by_dept,
        "par_type":       by_type,
    }


# ══════════════════════════════════════════════════
# GET /api/ws/stats
# ══════════════════════════════════════════════════
@router.get("/api/ws/stats")
def ws_stats():
    """Nombre de connexions WebSocket actives par canal."""
    return {
        "total":     manager.connection_count(),
        "dashboard": manager.connection_count("dashboard"),
        "alertes":   manager.connection_count("alertes"),
        "feed":      manager.connection_count("feed"),
    }
