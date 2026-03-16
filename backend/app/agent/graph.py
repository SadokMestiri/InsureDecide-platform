"""
InsureDecide — Agent LangGraph
Architecture : router manuel (pas de bind_tools — non supporté par ChatOllama)

Flux :
  question → classifier mots-clés → outils en parallèle → synthèse Llama3
"""

import os
import logging
import asyncio
from typing import List

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_community.chat_models import ChatOllama

from app.agent.tools import kpi_tool, rag_tool, alerte_tool

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
LLM_MODEL   = os.getenv("LLM_MODEL",  "llama3")

SYSTEM_PROMPT = """Tu es l'assistant décisionnel d'InsureDecide, compagnie d'assurance tunisienne.
Tu aides le CEO à prendre des décisions stratégiques basées sur les données réelles.

Règles :
- Réponds TOUJOURS en français
- Cite les chiffres précis fournis dans le contexte (ne pas inventer)
- Structure : contexte -> analyse -> recommandation
- Si une situation est critique, dis-le clairement
- Sois concis et direct

Contexte entreprise :
- 3 départements : Automobile (~40K contrats), Vie (~25K), Immobilier (~20K)
- Données 2020-2024, monnaie TND (Dinar Tunisien)
- Situation : Vie déficitaire (RC ~125%), Automobile en crise résiliation (18%)
"""

KPI_KEYWORDS = [
    "kpi","chiffre","primes","sinistre","ratio","contrat","résiliation",
    "provision","fraude","performance","résultat","combien","quel est",
    "montant","taux","nombre","statistique","données","décembre","2024",
    "automobile","vie","immobilier","compare","évolution","tendance",
    "mois","année","état","santé financière","département"
]
RAG_KEYWORDS = [
    "explique","pourquoi","comment","définition","règle","seuil",
    "signifie","veut dire","c'est quoi","qu'est-ce","améliorer",
    "recommande","conseil","stratégie","action","mesure","contexte",
    "marché","tunisien","assurance","réglementation","norme"
]
ALERTE_KEYWORDS = [
    "alerte","risque","anomalie","critique","urgent","problème",
    "danger","warning","attention","préoccupant","fraude","déficitaire","perte"
]


def classify_question(question: str) -> List[str]:
    q = question.lower()
    kpi_score    = sum(1 for kw in KPI_KEYWORDS    if kw in q)
    rag_score    = sum(1 for kw in RAG_KEYWORDS    if kw in q)
    alerte_score = sum(1 for kw in ALERTE_KEYWORDS if kw in q)

    # Questions générales sur la compagnie → toujours tous les outils
    general_keywords = [
        "situation", "compagnie", "entreprise", "insuredecide", "global",
        "général", "globale", "ensemble", "tout", "bilan", "synthèse",
        "résumé", "actions", "urgent", "améliorer", "amélioration",
        "que faire", "quoi faire", "priorité", "plan", "feuille de route"
    ]
    is_general = any(kw in q for kw in general_keywords)

    if is_general:
        return ["kpi", "rag", "alerte"]

    tools = []
    # kpi_tool par défaut si aucun signal clair
    if kpi_score > 0 or (kpi_score == 0 and rag_score == 0 and alerte_score == 0):
        tools.append("kpi")
    if rag_score > 0:
        tools.append("rag")
    if alerte_score > 0:
        tools.append("alerte")
    # Question mixte données + explication → tout
    if kpi_score > 0 and rag_score > 0:
        tools = ["kpi", "rag", "alerte"]
    return tools or ["kpi"]


def _run_tool(tool_fn, arg):
    return tool_fn.invoke(arg)


async def invoke_agent(question: str, history: list = None) -> dict:
    llm = ChatOllama(
        base_url=OLLAMA_HOST,
        model=LLM_MODEL,
        temperature=0.1,
        num_predict=1024,
    )

    tools_to_call = classify_question(question)
    logger.info(f"Outils selectionnes : {tools_to_call}")

    loop = asyncio.get_event_loop()
    tasks      = []
    tools_used = []

    if "kpi" in tools_to_call:
        tasks.append(loop.run_in_executor(None, _run_tool, kpi_tool, question))
        tools_used.append("kpi_tool")
    if "rag" in tools_to_call:
        tasks.append(loop.run_in_executor(None, _run_tool, rag_tool, question))
        tools_used.append("rag_tool")
    if "alerte" in tools_to_call:
        tasks.append(loop.run_in_executor(None, _run_tool, alerte_tool, 3))
        tools_used.append("alerte_tool")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    context_parts = []
    steps = []
    for tool_name, result in zip(tools_used, results):
        if isinstance(result, Exception):
            logger.error(f"Outil {tool_name} erreur: {result}")
            steps.append(f"Erreur {tool_name}")
        else:
            context_parts.append(str(result))
            steps.append(f"{tool_name} : OK")

    context = "\n\n".join(context_parts)

    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    if history:
        for msg in history[-6:]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

    messages.append(HumanMessage(content=(
        f"Donnees InsureDecide disponibles :\n{context}\n\n"
        f"---\nQuestion du CEO : {question}\n\n"
        f"Reponds en francais de maniere structuree en utilisant les donnees ci-dessus."
    )))

    logger.info("Appel Llama3...")
    response = await loop.run_in_executor(None, llm.invoke, messages)
    answer   = response.content if hasattr(response, "content") else str(response)
    logger.info(f"Reponse : {len(answer)} caracteres")

    return {"answer": answer, "tools_used": tools_used, "steps": steps}