"""
InsureDecide — Routes Agent IA
POST /api/agent/chat    → question → réponse LangGraph
POST /api/agent/index   → déclenche l'indexation Qdrant
GET  /api/agent/status  → statut Ollama + Qdrant
"""

import logging
import httpx
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from app.agent.graph import invoke_agent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["Agent IA"])

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
QDRANT_URL  = os.getenv("QDRANT_URL",  "http://qdrant:6333")


# ── Schémas Pydantic
class ChatMessage(BaseModel):
    role:    str    # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    question: str
    history:  Optional[List[ChatMessage]] = []

class ChatResponse(BaseModel):
    answer:     str
    tools_used: List[str]
    steps:      List[str]

class IndexResponse(BaseModel):
    status:  str
    message: str


# ══════════════════════════════════════════════════
# POST /api/agent/chat
# ══════════════════════════════════════════════════
@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Envoie une question à l'agent LangGraph.
    L'agent utilise automatiquement les outils nécessaires (SQL, RAG, alertes)
    et retourne une réponse synthétisée par Llama3.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="La question ne peut pas être vide.")

    try:
        history = [{"role": m.role, "content": m.content} for m in (request.history or [])]
        result  = await invoke_agent(request.question, history)
        return ChatResponse(**result)

    except Exception as e:
        logger.error(f"Erreur agent chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur agent : {str(e)}")


# ══════════════════════════════════════════════════
# POST /api/agent/index
# ══════════════════════════════════════════════════
@router.post("/index", response_model=IndexResponse)
async def trigger_indexing():
    """
    Déclenche l'indexation complète des données dans Qdrant.
    À appeler après un import de nouvelles données.
    Opération longue (~2-3 minutes).
    """
    try:
        from app.agent.indexer import run_indexing
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_indexing)
        return IndexResponse(status="success", message="Indexation Qdrant terminée avec succès.")
    except Exception as e:
        logger.error(f"Erreur indexation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur indexation : {str(e)}")


# ══════════════════════════════════════════════════
# GET /api/agent/status
# ══════════════════════════════════════════════════
@router.get("/status")
async def agent_status():
    """Vérifie la disponibilité d'Ollama et Qdrant."""
    status = {"ollama": False, "qdrant": False, "model": None}

    async with httpx.AsyncClient(timeout=5) as client:
        # Vérifier Ollama
        try:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                status["ollama"] = True
                models = r.json().get("models", [])
                status["model"] = models[0]["name"] if models else None
        except Exception:
            pass

        # Vérifier Qdrant
        try:
            r = await client.get(f"{QDRANT_URL}/collections")
            if r.status_code == 200:
                status["qdrant"] = True
                collections = r.json().get("result", {}).get("collections", [])
                status["collections"] = [c["name"] for c in collections]
        except Exception:
            pass

    status["ready"] = status["ollama"] and status["qdrant"]
    return status
