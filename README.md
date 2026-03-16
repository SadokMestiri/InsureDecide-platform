# InsureDecide 🏦🤖
> Plateforme d'Aide à la Décision Stratégique pour Dirigeants d'Assurance  
> Propulsée par LLM + RAG + Multi-Agents IA

---

## 🚀 Démarrage rapide

### Prérequis
- Docker Desktop (Windows)
- Git
- 16 Go RAM recommandés (Ollama + tous les services)

### Lancer toute l'infrastructure

```bash
# 1. Cloner le projet
git clone <repo_url>
cd PFE

# 2. Copier les variables d'environnement
cp .env.example .env

# 3. Mettre les datasets dans le dossier DataSets/
# (clients.csv, contrats_*.csv, sinistres_*.csv, provisions.csv, kpis_mensuels.csv)

# 4. Lancer tous les services
docker compose up -d

# 5. Télécharger le modèle Mistral (première fois uniquement ~4Go)
docker exec insuredecide_ollama ollama pull mistral
```

### Vérifier que tout tourne
```bash
docker compose ps
```

---

## 🌐 URLs des services

| Service | URL | Identifiants |
|---|---|---|
| **Frontend** (Dashboard CEO) | http://localhost:3000 | - |
| **Backend API** (FastAPI docs) | http://localhost:8000/docs | - |
| **Airflow** (Pipelines) | http://localhost:8080 | admin / admin123 |
| **MLflow** (Modèles ML) | http://localhost:5000 | - |
| **MinIO** (Data Lake) | http://localhost:9001 | insuredecide_minio / insuredecide_minio_pass |
| **Grafana** (Monitoring) | http://localhost:3001 | admin / admin123 |
| **Qdrant** (Vecteurs RAG) | http://localhost:6333/dashboard | - |
| **Prometheus** (Métriques) | http://localhost:9090 | - |

---

## 📁 Structure du projet

```
PFE/
├── docker-compose.yml          # Infrastructure complète
├── .env.example                # Variables d'environnement (template)
├── .gitignore
├── DataSets/                   # Données simulées (non versionnées sur Git)
│   ├── clients.csv
│   ├── contrats_automobile.csv
│   ├── contrats_vie.csv
│   ├── contrats_immobilier.csv
│   ├── sinistres_automobile.csv
│   ├── sinistres_vie.csv
│   ├── sinistres_immobilier.csv
│   ├── provisions.csv
│   └── kpis_mensuels.csv
├── backend/                    # API FastAPI + Agents IA
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── sql/
│   │   └── init.sql            # Schéma PostgreSQL
│   └── app/
│       ├── main.py
│       ├── routers/
│       ├── agents/
│       ├── models/
│       └── services/
├── frontend/                   # Dashboard Next.js
│   ├── Dockerfile
│   └── ...
├── airflow/
│   ├── dags/                   # Pipelines de données
│   ├── logs/
│   └── plugins/
├── prometheus/
│   └── prometheus.yml
└── grafana/
```

---

## 🏗️ Stack Technologique

| Couche | Technologies |
|---|---|
| **Conteneurisation** | Docker + Docker Compose |
| **Ingestion** | Apache Airflow, Great Expectations |
| **Stockage** | PostgreSQL, MongoDB, MinIO, ClickHouse |
| **Vectoriel** | Qdrant |
| **IA / ML** | Mistral 7B (Ollama), LangChain, LangGraph |
| **MLOps** | MLflow, SHAP/LIME, Prometheus, Grafana |
| **Backend** | FastAPI, WebSockets, Celery, Redis |
| **Frontend** | Next.js |

---

## 📊 Départements couverts
- 🚗 **Automobile** — 40 000 contrats
- 💼 **Vie** — 25 000 contrats  
- 🏠 **Immobilier** — 20 000 contrats
- **Période** : 2020 → 2024 (5 ans)
