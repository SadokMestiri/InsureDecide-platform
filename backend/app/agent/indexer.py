"""
InsureDecide — Indexeur Qdrant
Vectorise les données métier PostgreSQL → Qdrant pour le RAG
Collections créées :
  - kpis_mensuels   : résumés textuels des KPIs par période/département
  - alertes_history : historique des anomalies détectées
  - regles_metier   : règles et seuils du domaine assurance
"""

import logging
import os
from typing import List, Dict, Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    CollectionInfo
)
from fastembed import TextEmbedding
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Config
QDRANT_URL   = os.getenv("QDRANT_URL",    "http://qdrant:6333")
DATABASE_URL = os.getenv("DATABASE_URL",  "postgresql://insuredecide_user:insuredecide_pass@postgres:5432/insuredecide")
EMBED_MODEL  = "BAAI/bge-small-en-v1.5"   # léger, rapide, CPU-friendly
VECTOR_SIZE  = 384

# ── Collections
COLLECTIONS = {
    "kpis_mensuels":   "KPIs mensuels résumés en langage naturel",
    "alertes_history": "Historique des alertes et anomalies détectées",
    "regles_metier":   "Règles métier et seuils du domaine assurance tunisienne",
}


def get_pg_connection():
    return psycopg2.connect(DATABASE_URL)


def init_qdrant(client: QdrantClient):
    """Crée les collections Qdrant si elles n'existent pas."""
    existing = {c.name for c in client.get_collections().collections}
    for name in COLLECTIONS:
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info(f"✅ Collection créée : {name}")
        else:
            logger.info(f"ℹ️  Collection existante : {name}")


def build_kpi_documents() -> List[Dict[str, Any]]:
    """
    Transforme les lignes kpis_mensuels en textes descriptifs riches.
    Chaque document = 1 mois × 1 département.
    """
    conn = get_pg_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT departement, annee, mois, periode,
               nb_contrats_actifs, primes_acquises_tnd,
               cout_sinistres_tnd, nb_sinistres,
               frequence_sinistres_pct, cout_moyen_sinistre_tnd,
               ratio_combine_pct, taux_resiliation_pct,
               provision_totale_tnd, nb_suspicions_fraude
        FROM kpis_mensuels
        ORDER BY annee, mois, departement
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()

    docs = []
    for r in rows:
        (dept, annee, mois, periode,
         nb_contrats, primes, cout_sin, nb_sin,
         freq_sin, cout_moy, ratio, resil,
         provision, fraudes) = r

        # Évaluation qualitative du ratio combiné
        if ratio > 110:
            eval_ratio = f"CRITIQUE (le département perd {ratio-100:.1f} centimes par dinar encaissé)"
        elif ratio > 95:
            eval_ratio = f"SOUS SURVEILLANCE ({ratio:.1f}% — approche du seuil de rentabilité)"
        else:
            eval_ratio = f"SAIN ({ratio:.1f}% — département rentable)"

        text = (
            f"Rapport mensuel {dept} — {periode} ({mois}/{annee}). "
            f"Le département {dept} compte {nb_contrats:,} contrats actifs. "
            f"Les primes acquises s'élèvent à {primes:,.0f} TND. "
            f"Le coût total des sinistres est {cout_sin:,.0f} TND pour {nb_sin} sinistres déclarés. "
            f"La fréquence sinistres est de {freq_sin:.2f}% avec un coût moyen par sinistre de {cout_moy:,.0f} TND. "
            f"Le ratio combiné est {eval_ratio}. "
            f"Le taux de résiliation est {resil:.1f}%. "
            f"Les provisions techniques totales sont {provision:,.0f} TND. "
            f"Suspicions de fraude détectées : {int(fraudes) if fraudes else 0}."
        )

        docs.append({
            "id":     f"{dept}_{annee}_{mois:02d}",
            "text":   text,
            "meta": {
                "departement": dept, "annee": annee, "mois": mois, "periode": periode,
                "ratio_combine_pct": float(ratio), "primes_acquises_tnd": float(primes),
                "taux_resiliation_pct": float(resil), "nb_sinistres": int(nb_sin),
            }
        })

    logger.info(f"📄 {len(docs)} documents KPI construits")
    return docs


def build_alerte_documents() -> List[Dict[str, Any]]:
    """
    Construit des documents textuels à partir des KPIs en détectant
    les périodes anomales (mêmes règles que kpi_service.py).
    """
    conn = get_pg_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT departement, periode, annee, mois,
               ratio_combine_pct, taux_resiliation_pct, nb_suspicions_fraude
        FROM kpis_mensuels
        WHERE ratio_combine_pct > 95
           OR taux_resiliation_pct > 15
           OR nb_suspicions_fraude >= 5
        ORDER BY annee DESC, mois DESC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()

    docs = []
    for i, r in enumerate(rows):
        dept, periode, annee, mois, ratio, resil, fraudes = r
        anomalies = []
        if ratio > 110:
            anomalies.append(f"ratio combiné CRITIQUE à {ratio:.1f}% (seuil : 110%)")
        elif ratio > 95:
            anomalies.append(f"ratio combiné en alerte à {ratio:.1f}% (seuil : 95%)")
        if resil > 15:
            anomalies.append(f"taux de résiliation élevé à {resil:.1f}% (seuil : 15%)")
        if fraudes and fraudes >= 5:
            anomalies.append(f"{int(fraudes)} suspicions de fraude détectées (seuil : 5)")

        text = (
            f"Alerte détectée — {dept} — période {periode}. "
            f"Anomalies identifiées : {'; '.join(anomalies)}. "
            f"Ce mois présente des indicateurs hors normes qui nécessitent une attention managériale."
        )

        docs.append({
            "id":   f"alerte_{dept}_{annee}_{mois:02d}",
            "text": text,
            "meta": {
                "departement": dept, "periode": periode, "annee": annee, "mois": mois,
                "ratio_combine_pct": float(ratio),
                "taux_resiliation_pct": float(resil),
                "nb_suspicions_fraude": int(fraudes) if fraudes else 0,
            }
        })

    logger.info(f"🚨 {len(docs)} documents Alerte construits")
    return docs


def build_regles_documents() -> List[Dict[str, Any]]:
    """
    Documents statiques de règles métier assurance tunisienne.
    Ce sont les connaissances de domaine injectées dans le RAG.
    """
    regles = [
        {
            "id": "regle_ratio_combine",
            "text": (
                "Le ratio combiné (Combined Ratio) est l'indicateur central de rentabilité technique en assurance. "
                "Il se calcule comme suit : (Coût Sinistres + Frais de Gestion) / Primes Acquises × 100. "
                "Un ratio inférieur à 95% indique une excellente rentabilité technique. "
                "Entre 95% et 100%, le département est rentable mais sous surveillance. "
                "Entre 100% et 110%, le département est en perte technique légère. "
                "Au-delà de 110%, le département est en situation critique : il perd plus qu'il ne gagne. "
                "Chez InsureDecide, le seuil d'alerte warning est 95% et le seuil critique est 110%."
            ),
        },
        {
            "id": "regle_resiliation",
            "text": (
                "Le taux de résiliation mesure le pourcentage de contrats résiliés par les clients sur une période. "
                "Un taux supérieur à 10% est préoccupant et indique un problème de satisfaction client. "
                "Un taux supérieur à 15% est critique et nécessite une action immédiate de rétention. "
                "Les causes habituelles sont : tarifs non compétitifs, mauvaise qualité de service, "
                "sinistres mal gérés, ou démarchage agressif de la concurrence. "
                "Chez InsureDecide, le seuil d'alerte critique est fixé à 15%."
            ),
        },
        {
            "id": "regle_fraude",
            "text": (
                "La fraude à l'assurance est un enjeu majeur en Tunisie, particulièrement dans l'automobile. "
                "Les indicateurs de suspicion de fraude incluent : sinistres répétitifs sur le même assuré, "
                "délais de déclaration anormalement longs, montants disproportionnés au véhicule, "
                "témoins récurrents dans plusieurs dossiers. "
                "Chez InsureDecide, un seuil de 5 suspicions par mois déclenche une alerte warning. "
                "Au-delà, une investigation approfondie est recommandée par le département Sinistres."
            ),
        },
        {
            "id": "regle_provisions",
            "text": (
                "Les provisions techniques sont les réserves financières obligatoires constituées par la compagnie. "
                "La Provision RBNS (Reported But Not Settled) couvre les sinistres déclarés mais non encore réglés. "
                "La Provision IBNR (Incurred But Not Reported) couvre les sinistres survenus mais pas encore déclarés. "
                "En Tunisie, ces provisions sont réglementées par le CGA (Comité Général des Assurances). "
                "Un niveau insuffisant de provisions expose la compagnie à un risque de solvabilité."
            ),
        },
        {
            "id": "regle_frequence_sinistres",
            "text": (
                "La fréquence des sinistres est le rapport entre le nombre de sinistres et le nombre de contrats exposés. "
                "En assurance automobile tunisienne, une fréquence de 0,30% à 0,50% est normale. "
                "En assurance vie, la fréquence est naturellement plus faible (0,05% à 0,15%). "
                "En assurance immobilière, la fréquence varie selon la région (risque inondation, incendie). "
                "Une hausse soudaine de fréquence peut signaler un problème de sélection des risques ou une fraude organisée."
            ),
        },
        {
            "id": "contexte_insuredecide",
            "text": (
                "InsureDecide est une compagnie d'assurance tunisienne opérant dans trois départements : "
                "Automobile (le plus grand avec ~40 000 contrats), Vie (~25 000 contrats), et Immobilier (~20 000 contrats). "
                "La compagnie dispose de données historiques de 2020 à 2024 (60 mois). "
                "Le chiffre d'affaires mensuel total avoisine 4,2 millions de TND en décembre 2024. "
                "Le département Vie présente un ratio combiné problématique autour de 125% fin 2024. "
                "Le département Automobile souffre d'un taux de résiliation élevé (~18%) depuis plusieurs mois. "
                "Le département Immobilier est globalement sain mais son ratio est en hausse récente."
            ),
        },
        {
            "id": "contexte_marche_tunisien",
            "text": (
                "Le marché de l'assurance tunisien est supervisé par le Comité Général des Assurances (CGA). "
                "Le secteur représente environ 2,5% du PIB tunisien. "
                "L'assurance automobile est obligatoire en Tunisie (responsabilité civile). "
                "La monnaie est le Dinar Tunisien (TND). "
                "Les principales compagnies concurrentes sont STAR, GAT, Comar, Maghrebia et Lloyd Tunisien. "
                "Le marché est en croissance mais confronté à des défis de rentabilité technique, "
                "notamment à cause de l'inflation des coûts de réparation automobile."
            ),
        },
    ]

    logger.info(f"📚 {len(regles)} règles métier construites")
    return regles


def index_documents(
    client: QdrantClient,
    embedder: TextEmbedding,
    collection: str,
    documents: List[Dict[str, Any]],
    batch_size: int = 50,
):
    """Vectorise et indexe les documents dans Qdrant par batches."""
    if not documents:
        logger.warning(f"⚠️  Aucun document à indexer pour {collection}")
        return

    texts = [d["text"] for d in documents]
    all_embeddings = list(embedder.embed(texts))

    points = []
    for i, (doc, emb) in enumerate(zip(documents, all_embeddings)):
        # Qdrant exige un id numérique ou UUID — on hash l'id string
        numeric_id = abs(hash(doc["id"])) % (2**63)
        points.append(PointStruct(
            id=numeric_id,
            vector=emb.tolist(),
            payload={"text": doc["text"], "doc_id": doc["id"], **doc.get("meta", {})}
        ))

    # Upload par batches
    for i in range(0, len(points), batch_size):
        batch = points[i:i+batch_size]
        client.upsert(collection_name=collection, points=batch)
        logger.info(f"  📤 {collection} : {min(i+batch_size, len(points))}/{len(points)} indexés")

    logger.info(f"✅ {collection} : {len(points)} documents indexés")


def run_indexing():
    """Point d'entrée principal — indexe toutes les collections."""
    logger.info("🚀 Démarrage indexation Qdrant — InsureDecide")

    client   = QdrantClient(url=QDRANT_URL)
    embedder = TextEmbedding(model_name=EMBED_MODEL)

    # 1. Initialiser les collections
    init_qdrant(client)

    # 2. Indexer les KPIs
    logger.info("📊 Indexation des KPIs mensuels...")
    kpi_docs = build_kpi_documents()
    index_documents(client, embedder, "kpis_mensuels", kpi_docs)

    # 3. Indexer les alertes
    logger.info("🚨 Indexation des alertes...")
    alerte_docs = build_alerte_documents()
    index_documents(client, embedder, "alertes_history", alerte_docs)

    # 4. Indexer les règles métier
    logger.info("📚 Indexation des règles métier...")
    regles_docs = build_regles_documents()
    index_documents(client, embedder, "regles_metier", regles_docs)

    # 5. Résumé final
    for name in COLLECTIONS:
        info = client.get_collection(name)
        logger.info(f"  📁 {name} : {info.points_count} points")

    logger.info("🎉 Indexation complète !")


if __name__ == "__main__":
    run_indexing()
