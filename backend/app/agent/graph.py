"""
InsureDecide — Agent LangGraph
Architecture : router manuel (pas de bind_tools — non supporté par ChatOllama)

Flux :
  question → classifier mots-clés → outils en parallèle → synthèse Llama3
"""

import os
import logging
import asyncio
import re
from typing import List

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_community.chat_models import ChatOllama

from app.agent.tools import (
    kpi_tool,
    rag_tool,
    alerte_tool,
    forecast_tool,
    anomaly_tool,
    drift_tool,
    explain_tool,
    segmentation_tool,
    client_tool,
    get_top_clients_claims,
    get_client_claims_profile,
    is_specific_client_question,
    sql_tool,
    data_query_tool,
    run_sql_analytics,
)

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
LLM_MODEL   = os.getenv("LLM_MODEL",  "llama3")

OUT_OF_SCOPE_MESSAGE = (
    "Je ne peux pas répondre à cette demande car elle est hors contexte d'InsureDecide. "
    "Je peux vous aider uniquement sur les sujets assurance (KPIs, sinistres, clients, alertes, "
    "prévisions, anomalies, drift, segmentation, explicabilité)."
)

SYSTEM_PROMPT = """Tu es l'assistant décisionnel d'InsureDecide, compagnie d'assurance tunisienne.
Tu aides le CEO à prendre des décisions stratégiques basées sur les données réelles.

Règles :
- Réponds TOUJOURS en français
- Cite les chiffres précis fournis dans le contexte (ne pas inventer)
- Structure : contexte -> analyse -> recommandation
- Si une situation est critique, dis-le clairement
- Sois concis et direct
- Si un outil retourne une erreur, indique explicitement la limite technique et n'invente jamais de résultats.
- N'invente jamais de noms/identifiants clients: si absents des données, indique-le explicitement.
- N'écris jamais de tableau Markdown libre; les tableaux/graphes sont générés séparément à partir de données structurées.
- N'écris jamais des placeholders comme [Image de visualisation].

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
FORECAST_KEYWORDS = [
    "prévision", "prevision", "forecast", "prévoir", "predire", "prédire",
    "mois prochain", "projection", "tendance future", "estimation"
]
ANOMALY_KEYWORDS = [
    "anomalie", "anomalies", "outlier", "suspect", "inhabituel", "isolation forest"
]
DRIFT_KEYWORDS = [
    "drift", "dérive", "derive", "distribution", "changement de données", "evidently"
]
EXPLAIN_KEYWORDS = [
    "expliquer le modèle", "shap", "importance", "feature importance", "interpréter le modèle",
    "pourquoi ce score", "explicabilité", "explicabilite"
]
SEGMENTATION_KEYWORDS = [
    "segment", "segmentation", "cluster", "clustering", "kmeans", "k-means",
    "tiers client", "profil client", "groupe client"
]
CLIENT_KEYWORDS = [
    "top client", "top clients", "sinistre par client",
    "meilleurs clients", "classement clients", "nom des clients", "plus de sinistres",
    "sinistres de", "sinistre de", "dans quel departement", "dans quel département"
]
SQL_KEYWORDS = [
    "sql", "requete", "requête", "gouvernorat", "region", "région",
    "ville", "zone", "localite", "localité", "sinistres par",
    "nombre total de clients", "combien de clients", "total clients", "total de clients", "nb clients"
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

GENERAL_BUSINESS_KEYWORDS = [
    "situation", "compagnie", "entreprise", "insuredecide", "global",
    "général", "globale", "ensemble", "tout", "bilan", "synthèse",
    "résumé", "actions", "urgent", "améliorer", "amélioration",
    "que faire", "quoi faire", "priorité", "plan", "feuille de route"
]


def _is_out_of_scope_question(question: str) -> bool:
    q = (question or "").strip().lower()
    if not q:
        return False

    domain_markers = [
        "assurance", "assureur", "insuredecide", "kpi", "sinistre", "sinistres",
        "contrat", "contrats", "client", "clients", "gouvernorat", "departement", "département",
        "automobile", "vie", "immobilier", "prime", "primes", "ratio", "résiliation", "resiliation",
        "provision", "fraude", "drift", "shap", "segmentation", "cluster", "prévision", "prevision",
        "alerte", "alertes", "denodo", "postgres", "sql", "tableau", "visualisation",
    ]

    intent_markers = (
        KPI_KEYWORDS
        + RAG_KEYWORDS
        + ALERTE_KEYWORDS
        + FORECAST_KEYWORDS
        + ANOMALY_KEYWORDS
        + DRIFT_KEYWORDS
        + EXPLAIN_KEYWORDS
        + SEGMENTATION_KEYWORDS
        + CLIENT_KEYWORDS
        + SQL_KEYWORDS
        + GENERAL_BUSINESS_KEYWORDS
    )

    if any(m in q for m in domain_markers):
        return False
    if any(m in q for m in intent_markers):
        return False

    return True


def _extract_n_clusters(question: str, default: int = 4) -> int:
    q = (question or "").lower()
    for n in [2, 3, 4, 5, 6, 7, 8]:
        if f"{n} cluster" in q or f"{n} segment" in q:
            return n
    return default


def _extract_top_n(question: str, default: int = 5) -> int:
    q = (question or "").lower()
    m = re.search(r"top\s*(\d{1,2})", q)
    if m:
        return max(1, min(20, int(m.group(1))))
    for n in [3, 5, 10, 15, 20]:
        if str(n) in q:
            return n
    return default


def _extract_forecast_params(question: str):
    q = (question or "").lower()
    dept = "Automobile"
    if "vie" in q:
        dept = "Vie"
    elif "immo" in q or "immobilier" in q:
        dept = "Immobilier"

    indicateur = "primes_acquises_tnd"
    if "sinistre" in q and ("nb" in q or "nombre" in q):
        indicateur = "nb_sinistres"
    elif "ratio" in q or "combine" in q:
        indicateur = "ratio_combine_pct"
    elif "coût" in q or "cout" in q:
        indicateur = "cout_sinistres_tnd"

    nb_mois = 6
    for n in [3, 6, 9, 12]:
        if f"{n} mois" in q or f"{n}mois" in q:
            nb_mois = n
            break

    return dept, indicateur, nb_mois


def _extract_departement(question: str):
    q = (question or "").lower()
    if "vie" in q:
        return "Vie"
    if "immo" in q or "immobilier" in q:
        return "Immobilier"
    if "auto" in q or "automobile" in q:
        return "Automobile"
    return None


def _extract_model_name(question: str) -> str:
    q = (question or "").lower()
    return "fraude" if "fraude" in q else "resiliation"


def _build_charts(question: str, tools_used: List[str], steps: List[str]) -> list:
    charts = []
    ok_tools = {t for s, t in zip(steps, tools_used) if s.endswith(": OK")}

    try:
        if "data_query_tool" in ok_tools and detect_intent_metadata(question).get("intent") in {"geo_claims", "sql_analytics"}:
            sq = run_sql_analytics(question)
            if sq.get("status") == "ok" and sq.get("query_type") == "top_gouvernorat_sinistres":
                rows = sq.get("rows", [])
                if rows:
                    charts.append(
                        {
                            "id": "sql_top_gouvernorat",
                            "type": "bar",
                            "title": "Sinistres par gouvernorat",
                            "xKey": "gouvernorat",
                            "data": rows,
                            "series": [
                                {"key": "nb_sinistres", "name": "Nb sinistres", "color": "#dc2626"},
                                {"key": "cout_total_tnd", "name": "Cout total (TND)", "color": "#0ea5e9"},
                            ],
                            "meta": sq.get("scope", {}),
                        }
                    )
            if sq.get("status") == "ok" and sq.get("query_type") == "total_clients":
                rows = sq.get("rows", [])
                if rows:
                    charts.append(
                        {
                            "id": "sql_total_clients",
                            "type": "bar",
                            "title": "Nombre total de clients",
                            "xKey": "metric",
                            "data": rows,
                            "series": [
                                {"key": "value", "name": "Valeur", "color": "#0f766e"},
                            ],
                            "meta": sq.get("scope", {}),
                        }
                    )
    except Exception as e:
        logger.warning(f"Chart sql skipped: {e}")

    try:
        if "forecast_tool" in ok_tools:
            from app.ml.prophet_service import get_forecast

            dept, indicateur, nb_mois = _extract_forecast_params(question)
            fc = get_forecast(dept, indicateur, nb_mois)
            if not fc.get("error"):
                hist = fc.get("historique", [])[-12:]
                prev = fc.get("previsions", [])
                data = [
                    {
                        "periode": x.get("periode"),
                        "valeur": x.get("valeur"),
                        "type": "reel",
                    }
                    for x in hist
                ] + [
                    {
                        "periode": x.get("periode"),
                        "valeur": x.get("valeur"),
                        "valeur_min": x.get("valeur_min"),
                        "valeur_max": x.get("valeur_max"),
                        "type": "prevision",
                    }
                    for x in prev
                ]
                charts.append(
                    {
                        "id": "forecast_main",
                        "type": "line",
                        "title": f"Prévision {indicateur} - {dept}",
                        "xKey": "periode",
                        "data": data,
                        "series": [
                            {"key": "valeur", "name": "Valeur", "color": "#2563eb"},
                            {"key": "valeur_min", "name": "Min", "color": "#94a3b8"},
                            {"key": "valeur_max", "name": "Max", "color": "#64748b"},
                        ],
                    }
                )

                # Variante area pour visualiser la tendance de prévision.
                area_data = [x for x in data if x.get("type") == "prevision"]
                if area_data:
                    charts.append(
                        {
                            "id": "forecast_area",
                            "type": "area",
                            "title": f"Prévision (zone) {indicateur} - {dept}",
                            "xKey": "periode",
                            "data": area_data,
                            "series": [
                                {"key": "valeur", "name": "Prévision", "color": "#1d4ed8"},
                            ],
                        }
                    )
    except Exception as e:
        logger.warning(f"Chart forecast skipped: {e}")

    try:
        if "segmentation_tool" in ok_tools:
            from app.ml.segmentation_service import get_client_segmentation

            n_clusters = _extract_n_clusters(question, 4)
            dept = _extract_departement(question)
            seg = get_client_segmentation(n_clusters=n_clusters, limit_clients=12000, departement=dept)
            if seg.get("status") == "success":
                clusters = seg.get("clusters", [])
                bar_data = [
                    {
                        "cluster": f"C{c.get('cluster')}",
                        "label": c.get("segment_label"),
                        "nb_clients": c.get("nb_clients"),
                        "prime_moy": c.get("avg_prime_annuelle_tnd"),
                    }
                    for c in clusters
                ]
                charts.append(
                    {
                        "id": "segmentation_clusters",
                        "type": "bar",
                        "title": "Segments clients - Taille des clusters",
                        "xKey": "cluster",
                        "data": bar_data,
                        "series": [
                            {"key": "nb_clients", "name": "Clients", "color": "#7c3aed"},
                            {"key": "prime_moy", "name": "Prime moyenne", "color": "#16a34a"},
                        ],
                    }
                )

                # Camembert/donut de répartition des segments.
                pie_map = {}
                for c in clusters:
                    key = c.get("segment_label") or f"Cluster {c.get('cluster')}"
                    pie_map[key] = pie_map.get(key, 0) + int(c.get("nb_clients", 0) or 0)
                pie_data = [{"name": k, "value": v} for k, v in pie_map.items()]
                if pie_data:
                    charts.append(
                        {
                            "id": "segmentation_share",
                            "type": "pie",
                            "title": "Répartition des segments clients",
                            "data": pie_data,
                            "nameKey": "name",
                            "valueKey": "value",
                            "innerRadius": 45,
                            "outerRadius": 80,
                            "colors": ["#7c3aed", "#0ea5e9", "#16a34a", "#f59e0b", "#dc2626", "#14b8a6"],
                        }
                    )
    except Exception as e:
        logger.warning(f"Chart segmentation skipped: {e}")

    try:
        if "client_tool" in ok_tools:
            if is_specific_client_question(question):
                profile = get_client_claims_profile(question)
                if profile.get("status") == "ok":
                    dep_rows = profile.get("departements", [])
                    if dep_rows:
                        charts.append(
                            {
                                "id": "client_dept_distribution",
                                "type": "pie",
                                "title": f"Répartition des sinistres par département — {profile.get('client_name')}",
                                "data": [
                                    {
                                        "name": d.get("departement"),
                                        "value": d.get("nb_sinistres", 0),
                                        "part_pct": d.get("part_pct", 0),
                                    }
                                    for d in dep_rows
                                ],
                                "nameKey": "name",
                                "valueKey": "value",
                                "meta": {
                                    "client_id": profile.get("client_id"),
                                    "client_name": profile.get("client_name"),
                                    "nb_sinistres_total": profile.get("nb_sinistres_total"),
                                },
                                "colors": ["#dc2626", "#0ea5e9", "#16a34a", "#f59e0b"],
                            }
                        )
            else:
                dept = _extract_departement(question)
                top_n = _extract_top_n(question, default=5)
                cl = get_top_clients_claims(departement=dept, top_n=max(3, top_n))
                rows = cl.get("rows", [])
                if rows:
                    data = [
                        {
                            "client": r.get("client_id"),
                            "client_name": r.get("client_name"),
                            "nb_sinistres": r.get("nb_sinistres", 0),
                            "part_sinistres_pct": r.get("part_sinistres_pct", 0),
                        }
                        for r in rows[:10]
                    ]
                    charts.append(
                        {
                            "id": "client_top_claims",
                            "type": "bar",
                            "title": f"Top clients par nombre de sinistres ({cl.get('departement')})",
                            "xKey": "client",
                            "data": data,
                            "series": [
                                {"key": "nb_sinistres", "name": "Nb sinistres", "color": "#dc2626"},
                                {"key": "part_sinistres_pct", "name": "Part (%)", "color": "#0ea5e9"},
                            ],
                        }
                    )
    except Exception as e:
        logger.warning(f"Chart client skipped: {e}")

    try:
        if "anomaly_tool" in ok_tools:
            from app.ml.anomaly_service import detect_anomalies

            dept = _extract_departement(question)
            an = detect_anomalies(departement=dept, contamination=0.1)
            if not an.get("error"):
                anomalies = an.get("anomalies", [])[:8]
                if anomalies:
                    data = [
                        {
                            "label": f"{x.get('departement', '')} {x.get('periode', '')}",
                            "risk_score": x.get("risk_score", 0),
                            "ratio_combine_pct": x.get("ratio_combine_pct", 0),
                        }
                        for x in anomalies
                    ]
                    charts.append(
                        {
                            "id": "anomaly_top",
                            "type": "bar",
                            "title": "Anomalies détectées - Top risk score",
                            "xKey": "label",
                            "data": data,
                            "series": [
                                {"key": "risk_score", "name": "Risk score", "color": "#dc2626"},
                                {"key": "ratio_combine_pct", "name": "Ratio combiné %", "color": "#f59e0b"},
                            ],
                        }
                    )

                    # Camembert par département pour lecture managériale.
                    dept_counts = {}
                    for x in anomalies:
                        d = x.get("departement") or "Inconnu"
                        dept_counts[d] = dept_counts.get(d, 0) + 1
                    pie_data = [{"name": k, "value": v} for k, v in dept_counts.items()]
                    if pie_data:
                        charts.append(
                            {
                                "id": "anomaly_dept_share",
                                "type": "pie",
                                "title": "Répartition des anomalies par département",
                                "data": pie_data,
                                "nameKey": "name",
                                "valueKey": "value",
                                "colors": ["#dc2626", "#f59e0b", "#0ea5e9", "#16a34a"],
                            }
                        )
    except Exception as e:
        logger.warning(f"Chart anomaly skipped: {e}")

    try:
        if "drift_tool" in ok_tools:
            from app.ml.drift_service import detect_drift

            dept = _extract_departement(question)
            dr = detect_drift(departement=dept, nb_mois_reference=12, nb_mois_courant=6)
            if not dr.get("error"):
                comp = dr.get("comparaison", [])
                if comp:
                    data = [
                        {
                            "feature": x.get("feature"),
                            "variation_pct": x.get("variation_pct", 0),
                        }
                        for x in comp[:7]
                    ]
                    charts.append(
                        {
                            "id": "drift_variation",
                            "type": "bar",
                            "title": "Data drift - Variation moyenne (%)",
                            "xKey": "feature",
                            "data": data,
                            "series": [
                                {"key": "variation_pct", "name": "Variation %", "color": "#0ea5e9"},
                            ],
                        }
                    )
    except Exception as e:
        logger.warning(f"Chart drift skipped: {e}")

    try:
        if "explain_tool" in ok_tools:
            from app.ml.shap_service import explain_prediction

            dept = _extract_departement(question) or "Automobile"
            model_name = _extract_model_name(question)
            dept_code = 0.0 if dept == "Automobile" else 1.0 if dept == "Vie" else 2.0
            input_values = {
                "ratio_combine_pct": 105.0,
                "primes_acquises_tnd": 1500000.0,
                "cout_sinistres_tnd": 900000.0,
                "nb_sinistres": 150.0,
                "provision_totale_tnd": 300000.0,
                "nb_suspicions_fraude": 3.0,
                "dept_code": dept_code,
                "mois": 12.0,
                "annee": 2024.0,
            }

            exp = explain_prediction(model_name, input_values)
            contributions = exp.get("contributions", [])
            if contributions:
                top = sorted(contributions, key=lambda x: abs(float(x.get("shap_value", 0))), reverse=True)[:6]
                data = [
                    {
                        "feature": x.get("label") or x.get("feature"),
                        "shap_value": float(x.get("shap_value", 0)),
                        "abs_impact": float(x.get("abs_impact", abs(float(x.get("shap_value", 0))))),
                    }
                    for x in top
                ]
                charts.append(
                    {
                        "id": "explain_shap",
                        "type": "bar",
                        "title": f"SHAP — facteurs principaux ({model_name})",
                        "xKey": "feature",
                        "data": data,
                        "series": [
                            {"key": "shap_value", "name": "Contribution SHAP", "color": "#16a34a"},
                            {"key": "abs_impact", "name": "Impact absolu", "color": "#64748b"},
                        ],
                    }
                )
    except Exception as e:
        logger.warning(f"Chart explain skipped: {e}")

    return charts


def _intent_scores(question: str) -> dict:
    q = (question or "").lower()
    kpi_raw = sum(1 for kw in KPI_KEYWORDS if kw in q)
    return {
        "kpi": int(round(kpi_raw * 0.5)),
        "rag": sum(1 for kw in RAG_KEYWORDS if kw in q),
        "alerte": sum(1 for kw in ALERTE_KEYWORDS if kw in q),
        "forecast": sum(1 for kw in FORECAST_KEYWORDS if kw in q),
        "anomaly": sum(1 for kw in ANOMALY_KEYWORDS if kw in q),
        "drift": sum(1 for kw in DRIFT_KEYWORDS if kw in q),
        "explain": sum(1 for kw in EXPLAIN_KEYWORDS if kw in q),
        "segmentation": sum(1 for kw in SEGMENTATION_KEYWORDS if kw in q),
        "client": sum(1 for kw in CLIENT_KEYWORDS if kw in q),
        "sql": sum(1 for kw in SQL_KEYWORDS if kw in q),
    }


def detect_intent_metadata(question: str) -> dict:
    scores = _intent_scores(question)
    q = (question or "").lower()

    # Priorité aux intentions spécialisées quand leurs mots-clés sont explicites.
    if any(kw in q for kw in ["shap", "explicabilité", "explicabilite", "importance"]):
        return {"intent": "explain", "intent_confidence": 0.9, "intent_scores": scores}
    if any(kw in q for kw in ["drift", "derive", "dérive", "evidently"]):
        return {"intent": "drift", "intent_confidence": 0.9, "intent_scores": scores}
    if any(kw in q for kw in ["segment", "segmentation", "cluster", "kmeans", "k-means"]):
        return {"intent": "segmentation", "intent_confidence": 0.9, "intent_scores": scores}
    if ("client" in q or "clients" in q) and any(k in q for k in ["nombre", "combien", "total", "nb"]) and "sinistre" not in q:
        return {"intent": "sql_analytics", "intent_confidence": 0.95, "intent_scores": scores}
    if "gouvernorat" in q and "sinistre" in q:
        return {"intent": "geo_claims", "intent_confidence": 0.95, "intent_scores": scores}
    if any(kw in q for kw in ["top client", "top clients", "plus de sinistres", "sinistre par client", "nom des clients"]):
        return {"intent": "client", "intent_confidence": 0.9, "intent_scores": scores}
    if any(kw in q for kw in ["prévision", "prevision", "forecast", "prévoir", "predire", "prédire"]):
        return {"intent": "forecast", "intent_confidence": 0.9, "intent_scores": scores}
    if any(kw in q for kw in ["anomalie", "anomalies", "outlier", "isolation forest"]):
        return {"intent": "anomaly", "intent_confidence": 0.9, "intent_scores": scores}

    total = sum(scores.values())
    primary_intent = max(scores, key=scores.get) if total > 0 else "kpi"
    top_score = scores.get(primary_intent, 0)
    confidence = round((top_score / total), 2) if total > 0 else 0.25

    general_keywords = [
        "situation", "compagnie", "entreprise", "insuredecide", "global",
        "général", "globale", "ensemble", "tout", "bilan", "synthèse",
        "résumé", "actions", "urgent", "améliorer", "amélioration",
        "que faire", "quoi faire", "priorité", "plan", "feuille de route"
    ]
    if any(kw in q for kw in general_keywords):
        primary_intent = "general"
        confidence = 0.9

    return {
        "intent": primary_intent,
        "intent_confidence": confidence,
        "intent_scores": scores,
    }


def _charts_to_markdown_table(charts: list, intent: str) -> str:
    if not charts:
        return ""

    def _num(v, decimals=1):
        try:
            return f"{float(v):.{decimals}f}"
        except Exception:
            return "-"

    def _int(v):
        try:
            return str(int(round(float(v))))
        except Exception:
            return "-"

    def _split_label(label):
        text = str(label or "").strip()
        parts = text.split()
        if len(parts) >= 2 and "-" in parts[-1]:
            return " ".join(parts[:-1]), parts[-1]
        return text or "-", "-"

    by_id = {c.get("id"): c for c in charts}

    if intent == "anomaly" and by_id.get("anomaly_top"):
        rows = by_id["anomaly_top"].get("data", [])[:8]
        if not rows:
            return ""
        lines = ["Departement ; Periode ; Risk Score ; Ratio Combine (%)"]
        for r in rows:
            dept, period = _split_label(r.get("label"))
            lines.append(f"{dept} ; {period} ; {_num(r.get('risk_score'))} ; {_num(r.get('ratio_combine_pct'))}")
        return "\n".join(lines)

    if intent == "segmentation" and by_id.get("segmentation_clusters"):
        rows = by_id["segmentation_clusters"].get("data", [])[:8]
        if not rows:
            return ""
        lines = ["Cluster ; Segment ; Nb Clients ; Prime Moyenne (TND)"]
        for r in rows:
            lines.append(f"{r.get('cluster','-')} ; {r.get('label','-')} ; {_int(r.get('nb_clients'))} ; {_num(r.get('prime_moy'))}")
        return "\n".join(lines)

    if intent == "forecast" and by_id.get("forecast_area"):
        rows = by_id["forecast_area"].get("data", [])[:12]
        if not rows:
            return ""
        lines = ["Periode ; Prevision ; Min ; Max"]
        for r in rows:
            lines.append(
                f"{r.get('periode','-')} ; {_num(r.get('valeur'))} ; {_num(r.get('valeur_min'))} ; {_num(r.get('valeur_max'))}"
            )
        return "\n".join(lines)

    if intent == "drift" and by_id.get("drift_variation"):
        rows = by_id["drift_variation"].get("data", [])[:10]
        if not rows:
            return ""
        lines = ["Feature ; Variation (%)"]
        for r in rows:
            lines.append(f"{r.get('feature','-')} ; {_num(r.get('variation_pct'))}")
        return "\n".join(lines)

    if intent == "explain" and by_id.get("explain_shap"):
        rows = by_id["explain_shap"].get("data", [])[:10]
        if not rows:
            return ""
        lines = ["Facteur ; Contribution SHAP ; Impact Absolu"]
        for r in rows:
            lines.append(f"{r.get('feature','-')} ; {_num(r.get('shap_value'), 3)} ; {_num(r.get('abs_impact'), 3)}")
        return "\n".join(lines)

    if intent == "client" and by_id.get("client_top_claims"):
        rows = by_id["client_top_claims"].get("data", [])[:10]
        if not rows:
            return ""
        lines = ["Client ID ; Nom Client ; Nb Sinistres ; Part Sinistres (%)"]
        for r in rows:
            lines.append(
                f"{r.get('client','-')} ; {r.get('client_name','-')} ; {_int(r.get('nb_sinistres'))} ; {_num(r.get('part_sinistres_pct'))}"
            )
        return "\n".join(lines)

    if intent == "client" and by_id.get("client_dept_distribution"):
        chart = by_id["client_dept_distribution"]
        rows = chart.get("data", [])
        if not rows:
            return ""
        lines = ["Departement ; Nb Sinistres ; Part (%)"]
        for r in rows:
            lines.append(f"{r.get('name','-')} ; {_int(r.get('value'))} ; {_num(r.get('part_pct'))}")
        return "\n".join(lines)

    if intent == "geo_claims" and by_id.get("sql_top_gouvernorat"):
        rows = by_id["sql_top_gouvernorat"].get("data", [])
        if not rows:
            return ""
        lines = ["Gouvernorat ; Nb Sinistres ; Part (%) ; Cout Total (TND)"]
        for r in rows:
            lines.append(
                f"{r.get('gouvernorat','-')} ; {_int(r.get('nb_sinistres'))} ; {_num(r.get('part_pct'))} ; {_num(r.get('cout_total_tnd'))}"
            )
        return "\n".join(lines)

    if intent == "sql_analytics" and by_id.get("sql_total_clients"):
        rows = by_id["sql_total_clients"].get("data", [])
        if not rows:
            return ""
        lines = ["Metrique ; Valeur"]
        for r in rows:
            lines.append(f"{r.get('metric','-')} ; {_int(r.get('value'))}")
        return "\n".join(lines)

    return ""


def _build_grounded_answer(question: str, intent: str, charts: list) -> str:
    by_id = {c.get("id"): c for c in (charts or [])}

    if intent == "geo_claims" and by_id.get("sql_top_gouvernorat"):
        chart = by_id["sql_top_gouvernorat"]
        rows = chart.get("data", [])
        if not rows:
            return "Aucune donnée sinistre disponible pour cette question."
        top = rows[0]
        meta = chart.get("meta", {})
        return "\n".join([
            "=== FICHE ANALYSE SINISTRES ===",
            f"Question: Gouvernorat avec le plus de sinistres",
            f"Departement: {meta.get('departement', 'Tous')}",
            f"Top N: {meta.get('top_n', len(rows))}",
            "",
            f"Reponse: {top.get('gouvernorat')} est le gouvernorat avec le plus de sinistres ({int(float(top.get('nb_sinistres', 0)))}).",
        ])

    if intent == "sql_analytics" and by_id.get("sql_total_clients"):
        chart = by_id["sql_total_clients"]
        rows = chart.get("data", [])
        if not rows:
            return "Aucune donnée client disponible pour cette question."
        value = int(float(rows[0].get("value", 0)))
        meta = chart.get("meta", {})
        return "\n".join([
            "=== FICHE ANALYSE CLIENTS ===",
            "Question: Nombre total de clients",
            f"Departement: {meta.get('departement', 'Tous')}",
            "",
            f"Reponse: Nombre total de clients = {value}.",
        ])

    if intent == "client" and by_id.get("client_dept_distribution"):
        chart = by_id["client_dept_distribution"]
        rows = chart.get("data", [])
        meta = chart.get("meta", {})
        if not rows:
            return "Contexte : Aucun sinistre client exploitable trouvé pour cette requête."
        lines = [
            "=== FICHE CLIENT ===",
            f"ID Client: {meta.get('client_id')}",
            f"Nom Client: {meta.get('client_name')}",
            f"Total Sinistres: {int(float(meta.get('nb_sinistres_total', 0)))}",
        ]
        return "\n".join(lines)

    if intent == "client" and by_id.get("client_top_claims"):
        chart = by_id["client_top_claims"]
        rows = chart.get("data", [])
        if not rows:
            return "Contexte : Aucune donnée client exploitable trouvée pour cette requête."
        lines = [
            "=== FICHE CLIENTS — TOP SINISTRES ===",
            f"Total Lignes: {len(rows)}",
        ]
        return "\n".join(lines)

    if intent == "segmentation" and by_id.get("segmentation_clusters"):
        rows = by_id["segmentation_clusters"].get("data", [])[:4]
        if not rows:
            return "Contexte : Segmentation indisponible pour le périmètre demandé."
        lines = [
            "Contexte : Segmentation clients calculée sur le périmètre demandé.",
            "",
            "Analyse :",
        ]
        for r in rows:
            lines.append(
                f"- {r.get('cluster')} ({r.get('label')}) : {int(float(r.get('nb_clients', 0)))} clients, prime moyenne {float(r.get('prime_moy', 0)):.2f} TND."
            )
        lines += [
            "",
            "Recommandation :",
            "- Activer des actions commerciales et risque par segment (VIP, Standard, A risque).",
            "- Suivre mensuellement la migration de clients entre segments.",
            "",
            "Note : Chiffres strictement alignés avec le tableau standardisé et les visualisations affichées.",
        ]
        return "\n".join(lines)

    if intent == "anomaly" and by_id.get("anomaly_top"):
        rows = by_id["anomaly_top"].get("data", [])[:3]
        if not rows:
            return "Contexte : Aucune anomalie majeure détectée sur le périmètre demandé."
        lines = [
            "Contexte : Détection d'anomalies sur les observations les plus risquées.",
            "",
            "Analyse :",
        ]
        for r in rows:
            lines.append(
                f"- {r.get('label')} : risk score {float(r.get('risk_score', 0)):.1f}, ratio combiné {float(r.get('ratio_combine_pct', 0)):.1f}%."
            )
        lines += [
            "",
            "Recommandation :",
            "- Traiter en priorité les cas avec risk score élevé et ratio combiné proche/supérieur aux seuils critiques.",
            "",
            "Note : Chiffres strictement alignés avec le tableau standardisé et les visualisations affichées.",
        ]
        return "\n".join(lines)

    if intent == "forecast" and by_id.get("forecast_area"):
        rows = by_id["forecast_area"].get("data", [])
        if not rows:
            return "Contexte : Prévision indisponible pour le périmètre demandé."
        first = rows[0]
        last = rows[-1]
        lines = [
            "Contexte : Prévision KPI calculée pour l'horizon demandé.",
            "",
            "Analyse :",
            f"- Début horizon ({first.get('periode')}) : {float(first.get('valeur', 0)):.1f}.",
            f"- Fin horizon ({last.get('periode')}) : {float(last.get('valeur', 0)):.1f}.",
            "- L'intervalle Min/Max est fourni dans le tableau standardisé.",
            "",
            "Recommandation :",
            "- Ajuster les objectifs budgétaires et capacité opérationnelle selon la tendance prévue.",
            "",
            "Note : Chiffres strictement alignés avec le tableau standardisé et les visualisations affichées.",
        ]
        return "\n".join(lines)

    if intent == "drift" and by_id.get("drift_variation"):
        rows = by_id["drift_variation"].get("data", [])[:5]
        if not rows:
            return "Contexte : Aucun signal de drift significatif sur le périmètre demandé."
        lines = [
            "Contexte : Analyse de dérive de données sur le périmètre demandé.",
            "",
            "Analyse :",
        ]
        for r in rows:
            lines.append(f"- {r.get('feature')} : variation moyenne {float(r.get('variation_pct', 0)):.2f}%.")
        lines += [
            "",
            "Recommandation :",
            "- Recalibrer les seuils et monitorer les features en variation forte.",
            "",
            "Note : Chiffres strictement alignés avec le tableau standardisé et les visualisations affichées.",
        ]
        return "\n".join(lines)

    if intent == "explain" and by_id.get("explain_shap"):
        rows = by_id["explain_shap"].get("data", [])[:5]
        if not rows:
            return "Contexte : Explicabilité indisponible sur le périmètre demandé."
        lines = [
            "Contexte : Explicabilité SHAP du modèle sur le scénario demandé.",
            "",
            "Analyse :",
        ]
        for r in rows:
            lines.append(
                f"- {r.get('feature')} : contribution SHAP {float(r.get('shap_value', 0)):.3f}, impact absolu {float(r.get('abs_impact', 0)):.3f}."
            )
        lines += [
            "",
            "Recommandation :",
            "- Cibler les actions métiers sur les facteurs avec impact absolu le plus élevé.",
            "",
            "Note : Chiffres strictement alignés avec le tableau standardisé et les visualisations affichées.",
        ]
        return "\n".join(lines)

    return ""


def _strip_freeform_tables(text: str) -> str:
    if not text:
        return text
    # Supprime tous les blocs fenced code (```...```), souvent utilisés par le LLM
    # pour simuler un tableau/graphique textuel.
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Supprime les blocs markdown ```...``` qui contiennent des tableaux.
    text = re.sub(r"```markdown\s*\|[\s\S]*?```", "", text, flags=re.IGNORECASE)
    # Supprime les tableaux markdown inline.
    text = re.sub(r"\n\|[^\n]*\|\n\|\s*---[\s\S]*?(?=\n\n|$)", "\n", text)
    # Nettoyage d'espaces multiples.
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _strip_redundant_visual_mentions(text: str) -> str:
    if not text:
        return text
    patterns = [
        r"\n\nPour[^\n]*visualisation[^\n]*:\s*",
        r"\n\nVoici[^\n]*visualisation[^\n]*:\s*",
        r"\n\nPour[^\n]*camembert[^\n]*:\s*",
        r"\n\nVoici[^\n]*camembert[^\n]*:\s*",
    ]
    for p in patterns:
        text = re.sub(p, "\n\n", text, flags=re.IGNORECASE)
    # Supprime aussi les mentions inline au milieu d'un paragraphe.
    text = re.sub(r"\bVoici[^\n\.]*visualisation[^\n\.]*\.?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bVoici[^\n\.]*camembert[^\n\.]*\.?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPour[^\n\.]*visualisation[^\n\.]*\.?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPour[^\n\.]*camembert[^\n\.]*\.?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _strip_visualization_lines(text: str) -> str:
    if not text:
        return text
    kept = []
    for line in text.split("\n"):
        ll = line.strip().lower()
        if "visualisation" in ll or "camembert" in ll:
            continue
        if ll.startswith("note :") and "visualisation" in ll:
            continue
        kept.append(line)
    text = "\n".join(kept)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def classify_question(question: str) -> List[str]:
    q = question.lower()
    kpi_score    = sum(1 for kw in KPI_KEYWORDS    if kw in q)
    rag_score    = sum(1 for kw in RAG_KEYWORDS    if kw in q)
    alerte_score = sum(1 for kw in ALERTE_KEYWORDS if kw in q)
    forecast_score = sum(1 for kw in FORECAST_KEYWORDS if kw in q)
    anomaly_score = sum(1 for kw in ANOMALY_KEYWORDS if kw in q)
    drift_score = sum(1 for kw in DRIFT_KEYWORDS if kw in q)
    explain_score = sum(1 for kw in EXPLAIN_KEYWORDS if kw in q)
    segmentation_score = sum(1 for kw in SEGMENTATION_KEYWORDS if kw in q)
    client_score = sum(1 for kw in CLIENT_KEYWORDS if kw in q)
    sql_score = sum(1 for kw in SQL_KEYWORDS if kw in q)

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
    if kpi_score > 0 or (
        kpi_score == 0
        and rag_score == 0
        and alerte_score == 0
        and forecast_score == 0
        and anomaly_score == 0
        and drift_score == 0
        and explain_score == 0
        and segmentation_score == 0
        and client_score == 0
        and sql_score == 0
    ):
        tools.append("kpi")
    if rag_score > 0:
        tools.append("rag")
    if alerte_score > 0:
        tools.append("alerte")
    if forecast_score > 0:
        tools.append("forecast")
    if anomaly_score > 0:
        tools.append("anomaly")
    if drift_score > 0:
        tools.append("drift")
    if explain_score > 0:
        tools.append("explain")
    if segmentation_score > 0:
        tools.append("segmentation")
    if client_score > 0:
        tools.append("client")
    if sql_score > 0:
        tools.append("sql")
    # Question mixte donnees + explication metier
    if kpi_score > 0 and rag_score > 0 and forecast_score == 0 and anomaly_score == 0 and drift_score == 0 and explain_score == 0 and segmentation_score == 0:
        tools = ["kpi", "rag", "alerte"]

    # Question explicabilite modele: outil dedie + contexte KPI
    if explain_score > 0 and forecast_score == 0 and anomaly_score == 0 and drift_score == 0 and segmentation_score == 0:
        tools = ["kpi", "explain"]

    # Question segmentation: outil dedie + contexte KPI
    if segmentation_score > 0 and forecast_score == 0 and anomaly_score == 0 and drift_score == 0:
        tools = ["kpi", "segmentation"]

    # Question client détaillée: privilégier l'outil dédié pour éviter les réponses vagues.
    if client_score > 0 and segmentation_score == 0 and forecast_score == 0 and anomaly_score == 0 and drift_score == 0 and explain_score == 0:
        tools = ["client"]

    if sql_score > 0 and "gouvernorat" in q and "sinistre" in q:
        tools = ["sql"]
    if ("client" in q or "clients" in q) and any(k in q for k in ["nombre", "combien", "total", "nb"]) and "sinistre" not in q:
        tools = ["sql"]

    return tools or ["kpi"]


def _run_tool(tool_fn, arg):
    return tool_fn.invoke(arg)


async def invoke_agent(question: str, history: list = None, skip_llm: bool = False) -> dict:
    llm = ChatOllama(
        base_url=OLLAMA_HOST,
        model=LLM_MODEL,
        temperature=0.1,
        num_predict=1024,
    )

    tools_to_call = classify_question(question)
    intent_meta = detect_intent_metadata(question)

    if _is_out_of_scope_question(question):
        return {
            "answer": OUT_OF_SCOPE_MESSAGE,
            "tools_used": [],
            "steps": ["Hors contexte assurance"],
            "charts": [],
            "intent": "out_of_scope",
            "intent_confidence": 1.0,
        }

    logger.info(f"Outils selectionnes : {tools_to_call}")

    loop = asyncio.get_event_loop()
    tasks      = []
    tools_used = []

    if "kpi" in tools_to_call or "sql" in tools_to_call:
        tasks.append(loop.run_in_executor(None, _run_tool, data_query_tool, question))
        tools_used.append("data_query_tool")
    if "rag" in tools_to_call:
        tasks.append(loop.run_in_executor(None, _run_tool, rag_tool, question))
        tools_used.append("rag_tool")
    if "alerte" in tools_to_call:
        tasks.append(loop.run_in_executor(None, _run_tool, alerte_tool, {"nb_mois": 3}))
        tools_used.append("alerte_tool")
    if "forecast" in tools_to_call:
        tasks.append(loop.run_in_executor(None, _run_tool, forecast_tool, question))
        tools_used.append("forecast_tool")
    if "anomaly" in tools_to_call:
        tasks.append(loop.run_in_executor(None, _run_tool, anomaly_tool, question))
        tools_used.append("anomaly_tool")
    if "drift" in tools_to_call:
        tasks.append(loop.run_in_executor(None, _run_tool, drift_tool, question))
        tools_used.append("drift_tool")
    if "explain" in tools_to_call:
        tasks.append(loop.run_in_executor(None, _run_tool, explain_tool, question))
        tools_used.append("explain_tool")
    if "segmentation" in tools_to_call:
        tasks.append(loop.run_in_executor(None, _run_tool, segmentation_tool, question))
        tools_used.append("segmentation_tool")
    if "client" in tools_to_call:
        tasks.append(loop.run_in_executor(None, _run_tool, client_tool, question))
        tools_used.append("client_tool")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    context_parts = []
    steps = []
    tool_outputs = {}
    for tool_name, result in zip(tools_used, results):
        if isinstance(result, Exception):
            logger.error(f"Outil {tool_name} erreur: {result}")
            steps.append(f"Erreur {tool_name}")
        else:
            result_text = str(result)
            tool_outputs[tool_name] = result_text
            context_parts.append(result_text)
            if result_text.strip().lower().startswith("erreur"):
                steps.append(f"Erreur {tool_name}")
            else:
                steps.append(f"{tool_name} : OK")

    context = "\n\n".join(context_parts)

    specialist_tools = {
        "forecast_tool",
        "anomaly_tool",
        "drift_tool",
        "explain_tool",
        "segmentation_tool",
        "client_tool",
        "data_query_tool",
    }
    specialist_ok = any(
        s.endswith(": OK") and t in specialist_tools
        for s, t in zip(steps, tools_used)
    )
    specialist_requested = any(t in specialist_tools for t in tools_used)

    if specialist_requested and not specialist_ok:
        return {
            "answer": (
                "Je ne peux pas fournir une analyse spécialisée fiable pour cette demande car "
                "l'outil ML requis a retourné une erreur technique. "
                "Merci de réessayer dans quelques instants ou de vérifier l'état du backend ML."
            ),
            "tools_used": tools_used,
            "steps": steps,
            "charts": [],
            "intent": intent_meta["intent"],
            "intent_confidence": intent_meta["intent_confidence"],
        }

    should_skip_llm = skip_llm or intent_meta["intent"] in {"client", "geo_claims", "sql_analytics"}

    if should_skip_llm:
        answer = ""
    else:
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

    charts = _build_charts(question, tools_used, steps)

    # Garde-fou client: si pas de chart robuste, conserver la sortie factuelle de l'outil
    # et éviter une reformulation LLM potentiellement incohérente.
    if intent_meta["intent"] == "client" and not charts and "client_tool" in tool_outputs:
        answer = tool_outputs["client_tool"]
    if intent_meta["intent"] == "geo_claims" and "data_query_tool" in tool_outputs and not answer:
        answer = tool_outputs["data_query_tool"]
    if intent_meta["intent"] == "sql_analytics" and "data_query_tool" in tool_outputs and not answer:
        answer = tool_outputs["data_query_tool"]

    grounded_answer = _build_grounded_answer(question, intent_meta["intent"], charts)
    if grounded_answer:
        answer = grounded_answer
    ql = (question or "").lower()
    wants_table = (
        intent_meta["intent"] in {"client", "geo_claims", "sql_analytics"}
        or any(k in ql for k in ["tableau", "table", "visualisation", "camembert", "graphique"])
    )
    table_md = _charts_to_markdown_table(charts, intent_meta["intent"])
    if wants_table and table_md:
        answer = _strip_freeform_tables(answer)
        answer = _strip_redundant_visual_mentions(answer)
        answer = _strip_visualization_lines(answer)
        answer += "\n\nTableau standardise:\n\n" + table_md
    answer = answer.replace("[Image de visualisation]", "")

    return {
        "answer": answer,
        "tools_used": tools_used,
        "steps": steps,
        "charts": charts,
        "intent": intent_meta["intent"],
        "intent_confidence": intent_meta["intent_confidence"],
    }