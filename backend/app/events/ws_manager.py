"""
InsureDecide — WebSocket Manager
Gère les connexions WebSocket et le broadcast des données en temps réel.
"""

import logging
import json
import asyncio
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Gestionnaire de connexions WebSocket multi-clients."""

    def __init__(self):
        # Connexions actives par canal
        self.channels: Dict[str, Set[WebSocket]] = {
            "dashboard": set(),
            "alertes":   set(),
            "feed":      set(),
        }

    async def connect(self, websocket: WebSocket, channel: str = "dashboard"):
        await websocket.accept()
        if channel not in self.channels:
            self.channels[channel] = set()
        self.channels[channel].add(websocket)
        total = sum(len(v) for v in self.channels.values())
        logger.info(f"🔌 WebSocket connecté — canal:{channel} | total:{total}")

    def disconnect(self, websocket: WebSocket, channel: str = "dashboard"):
        self.channels.get(channel, set()).discard(websocket)
        total = sum(len(v) for v in self.channels.values())
        logger.info(f"🔌 WebSocket déconnecté — canal:{channel} | total:{total}")

    async def broadcast(self, channel: str, data: dict):
        """Envoie un message à tous les clients d'un canal."""
        sockets = list(self.channels.get(channel, set()))
        if not sockets:
            return

        message = json.dumps(data, ensure_ascii=False, default=str)
        dead = []
        for ws in sockets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        # Nettoyer les connexions mortes
        for ws in dead:
            self.channels[channel].discard(ws)

    async def broadcast_all(self, data: dict):
        """Envoie à tous les canaux."""
        for channel in self.channels:
            await self.broadcast(channel, data)

    def connection_count(self, channel: str = None) -> int:
        if channel:
            return len(self.channels.get(channel, set()))
        return sum(len(v) for v in self.channels.values())


# Instance globale unique
manager = ConnectionManager()
