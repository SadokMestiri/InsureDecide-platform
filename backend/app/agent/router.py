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
    charts:     Optional[list] = []
    intent:     Optional[str] = None
    intent_confidence: Optional[float] = None

class IndexResponse(BaseModel):
    status:  str
    message: str


class SmokeCaseResult(BaseModel):
    name: str
    question: str
    expected_intent: str
    got_intent: Optional[str] = None
    expected_tool: str
    tool_ok: bool
    expected_chart: bool
    chart_ok: bool
    intent_ok: bool
    passed: bool
    steps: List[str] = []


class SmokeEvalResponse(BaseModel):
    status: str
    passed: int
    total: int
    success_rate: float
    details: List[SmokeCaseResult]


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


@router.get("/eval/smoke", response_model=SmokeEvalResponse)
async def agent_eval_smoke():
    """
    Exécute un smoke test de l'orchestrateur IA sur des prompts canoniques.
    Vérifie : intent, outil spécialiste, chart attendu.
    """
    cases = [
        {
            "name": "forecast",
            "question": "Fais une prevision des primes automobile pour 6 mois avec visualisation",
            "expected_intent": "forecast",
            "expected_tool": "forecast_tool",
            "expected_chart": True,
        },
        {
            "name": "anomaly",
            "question": "Detecte les anomalies recentes sur le departement Vie avec visualisation",
            "expected_intent": "anomaly",
            "expected_tool": "anomaly_tool",
            "expected_chart": True,
        },
        {
            "name": "drift",
            "question": "Montre moi le drift data de l automobile avec visualisation",
            "expected_intent": "drift",
            "expected_tool": "drift_tool",
            "expected_chart": True,
        },
        {
            "name": "explain",
            "question": "Explique le modele fraude avec shap et visualisation",
            "expected_intent": "explain",
            "expected_tool": "explain_tool",
            "expected_chart": True,
        },
        {
            "name": "segmentation",
            "question": "Segmente mes clients en 4 clusters et montre les segments",
            "expected_intent": "segmentation",
            "expected_tool": "segmentation_tool",
            "expected_chart": True,
        },
        {
            "name": "client_top",
            "question": "Donne le top 3 clients avec le plus de sinistres",
            "expected_intent": "client",
            "expected_tool": "client_tool",
            "expected_chart": True,
        },
    ]

    results: List[SmokeCaseResult] = []
    for c in cases:
        try:
            res = await invoke_agent(c["question"], history=[], skip_llm=True)
            steps = res.get("steps", [])
            tools_used = res.get("tools_used", [])
            charts = res.get("charts", [])

            tool_ok = (
                c["expected_tool"] in tools_used
                and any(s == f"{c['expected_tool']} : OK" for s in steps)
            )
            chart_ok = (len(charts) > 0) if c["expected_chart"] else True
            got_intent = res.get("intent")
            intent_ok = got_intent == c["expected_intent"]
            passed = tool_ok and chart_ok and intent_ok

            results.append(
                SmokeCaseResult(
                    name=c["name"],
                    question=c["question"],
                    expected_intent=c["expected_intent"],
                    got_intent=got_intent,
                    expected_tool=c["expected_tool"],
                    tool_ok=tool_ok,
                    expected_chart=c["expected_chart"],
                    chart_ok=chart_ok,
                    intent_ok=intent_ok,
                    passed=passed,
                    steps=steps,
                )
            )
        except Exception as e:
            results.append(
                SmokeCaseResult(
                    name=c["name"],
                    question=c["question"],
                    expected_intent=c["expected_intent"],
                    got_intent=None,
                    expected_tool=c["expected_tool"],
                    tool_ok=False,
                    expected_chart=c["expected_chart"],
                    chart_ok=False,
                    intent_ok=False,
                    passed=False,
                    steps=[f"Erreur smoke: {str(e)}"],
                )
            )

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    success_rate = round((passed / total) * 100, 1) if total else 0.0

    return SmokeEvalResponse(
        status="ok" if passed == total else "warning",
        passed=passed,
        total=total,
        success_rate=success_rate,
        details=results,
    )
