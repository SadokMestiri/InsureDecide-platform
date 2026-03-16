"""
InsureDecide — Outils LangGraph
Trois outils que les sous-agents peuvent appeler :
  - kpi_tool    : requête SQL directe sur PostgreSQL
  - rag_tool    : recherche sémantique dans Qdrant
  - alerte_tool : récupère les alertes actives
"""

import os
import logging
from typing import Optional
from langchain_core.tools import tool
from qdrant_client import QdrantClient
from fastembed import TextEmbedding
import psycopg2

logger = logging.getLogger(__name__)

QDRANT_URL   = os.getenv("QDRANT_URL",   "http://qdrant:6333")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://insuredecide_user:insuredecide_pass@postgres:5432/insuredecide")
EMBED_MODEL  = "BAAI/bge-small-en-v1.5"

# Singletons (initialisés une fois au démarrage)
_qdrant_client: Optional[QdrantClient]  = None
_embedder:      Optional[TextEmbedding] = None


def get_qdrant() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=QDRANT_URL)
    return _qdrant_client


def get_embedder() -> TextEmbedding:
    global _embedder
    if _embedder is None:
        _embedder = TextEmbedding(model_name=EMBED_MODEL)
    return _embedder


def get_pg():
    return psycopg2.connect(DATABASE_URL)


# ══════════════════════════════════════════════════
# OUTIL 1 — KPI SQL
# ══════════════════════════════════════════════════
@tool
def kpi_tool(question: str) -> str:
    """
    Interroge la base PostgreSQL pour répondre à des questions sur les KPIs
    d'InsureDecide. Retourne les données chiffrées en langage naturel.
    Utilise cet outil pour : chiffres précis, comparaisons entre périodes,
    classements, totaux, moyennes.
    """
    try:
        conn = get_pg()
        cur  = conn.cursor()

        # Données dernière période disponible
        cur.execute("""
            SELECT departement, periode, annee, mois,
                   nb_contrats_actifs, primes_acquises_tnd,
                   cout_sinistres_tnd, nb_sinistres,
                   ratio_combine_pct, taux_resiliation_pct,
                   provision_totale_tnd, nb_suspicions_fraude,
                   cout_moyen_sinistre_tnd
            FROM kpis_mensuels
            WHERE (annee, mois) = (
                SELECT annee, mois FROM kpis_mensuels
                ORDER BY annee DESC, mois DESC LIMIT 1
            )
            ORDER BY departement
        """)
        rows = cur.fetchall()

        # Données évolution sur 12 derniers mois
        cur.execute("""
            SELECT departement, periode, ratio_combine_pct,
                   primes_acquises_tnd, cout_sinistres_tnd, taux_resiliation_pct
            FROM kpis_mensuels
            ORDER BY annee DESC, mois DESC
            LIMIT 36
        """)
        evolution = cur.fetchall()
        cur.close(); conn.close()

        # Formatter les données pour le LLM
        context = "=== DONNÉES KPIS INSUREDECIDE — DERNIÈRE PÉRIODE ===\n\n"
        for r in rows:
            (dept, periode, annee, mois, contrats, primes, cout_sin, nb_sin,
             ratio, resil, provision, fraudes, cout_moy) = r
            context += (
                f"DÉPARTEMENT {dept} — {periode}\n"
                f"  Contrats actifs      : {contrats:,}\n"
                f"  Primes acquises      : {primes:,.0f} TND\n"
                f"  Coût sinistres       : {cout_sin:,.0f} TND\n"
                f"  Nombre sinistres     : {int(nb_sin)}\n"
                f"  Coût moyen sinistre  : {cout_moy:,.0f} TND\n"
                f"  Ratio combiné        : {ratio:.1f}%\n"
                f"  Taux résiliation     : {resil:.1f}%\n"
                f"  Provisions           : {provision:,.0f} TND\n"
                f"  Suspicions fraude    : {int(fraudes) if fraudes else 0}\n\n"
            )

        context += "=== ÉVOLUTION RÉCENTE (12 DERNIERS MOIS) ===\n"
        for r in evolution[:12]:
            dept, periode, ratio, primes, cout, resil = r
            context += f"  {dept} {periode} → RC:{ratio:.1f}% | Primes:{primes:,.0f} | Résil:{resil:.1f}%\n"

        return context

    except Exception as e:
        logger.error(f"kpi_tool error: {e}")
        return f"Erreur lors de la récupération des KPIs : {str(e)}"


# ══════════════════════════════════════════════════
# OUTIL 2 — RAG Qdrant
# ══════════════════════════════════════════════════
@tool
def rag_tool(query: str) -> str:
    """
    Recherche sémantique dans la base de connaissances d'InsureDecide.
    Contient : règles métier assurance, historique KPIs, alertes passées.
    Utilise cet outil pour : explications, contexte, règles, recommandations,
    tendances historiques, définitions métier.
    """
    try:
        client   = get_qdrant()
        embedder = get_embedder()

        query_vector = list(embedder.embed([query]))[0].tolist()

        results = []
        for collection in ["regles_metier", "kpis_mensuels", "alertes_history"]:
            hits = client.search(
                collection_name=collection,
                query_vector=query_vector,
                limit=3,
                score_threshold=0.35,
            )
            for hit in hits:
                results.append({
                    "score":      hit.score,
                    "collection": collection,
                    "text":       hit.payload.get("text", ""),
                    "meta":       {k: v for k, v in hit.payload.items() if k != "text"},
                })

        # Trier par score et garder les 6 meilleurs
        results.sort(key=lambda x: x["score"], reverse=True)
        top = results[:6]

        if not top:
            return "Aucune information pertinente trouvée dans la base de connaissances."

        context = "=== RÉSULTATS DE LA BASE DE CONNAISSANCES ===\n\n"
        for i, r in enumerate(top, 1):
            context += f"[{i}] Source: {r['collection']} (pertinence: {r['score']:.2f})\n"
            context += f"{r['text']}\n\n"

        return context

    except Exception as e:
        logger.error(f"rag_tool error: {e}")
        return f"Erreur lors de la recherche RAG : {str(e)}"


# ══════════════════════════════════════════════════
# OUTIL 3 — Alertes actives
# ══════════════════════════════════════════════════
@tool
def alerte_tool(nb_mois: int = 3) -> str:
    """
    Retourne les alertes et anomalies détectées sur les derniers mois.
    Utilise cet outil pour : questions sur les risques actuels, anomalies,
    situations critiques, recommandations d'actions urgentes.
    """
    try:
        conn = get_pg()
        cur  = conn.cursor()

        cur.execute("""
            SELECT departement, periode, annee, mois,
                   ratio_combine_pct, taux_resiliation_pct, nb_suspicions_fraude
            FROM kpis_mensuels
            WHERE (annee * 12 + mois) >= (
                SELECT MAX(annee * 12 + mois) - %s FROM kpis_mensuels
            )
            ORDER BY annee DESC, mois DESC
        """, (nb_mois,))
        rows = cur.fetchall()
        cur.close(); conn.close()

        alertes = []
        for r in rows:
            dept, periode, annee, mois, ratio, resil, fraudes = r
            if ratio > 110:
                alertes.append(f"🔴 CRITIQUE — {dept} {periode} : ratio combiné {ratio:.1f}% (seuil 110%)")
            elif ratio > 95:
                alertes.append(f"🟡 WARNING  — {dept} {periode} : ratio combiné {ratio:.1f}% (seuil 95%)")
            if resil > 15:
                alertes.append(f"🔴 CRITIQUE — {dept} {periode} : résiliation {resil:.1f}% (seuil 15%)")
            if fraudes and fraudes >= 5:
                alertes.append(f"🟡 WARNING  — {dept} {periode} : {int(fraudes)} suspicions fraude (seuil 5)")

        if not alertes:
            return "✅ Aucune anomalie détectée sur les derniers mois. Tous les indicateurs sont dans les seuils normaux."

        context = f"=== ALERTES ACTIVES — {nb_mois} DERNIERS MOIS ===\n\n"
        context += "\n".join(alertes)
        context += f"\n\nTotal : {len(alertes)} alerte(s) détectée(s)."
        return context

    except Exception as e:
        logger.error(f"alerte_tool error: {e}")
        return f"Erreur lors de la récupération des alertes : {str(e)}"


# Liste des outils disponibles pour LangGraph
TOOLS = [kpi_tool, rag_tool, alerte_tool]
