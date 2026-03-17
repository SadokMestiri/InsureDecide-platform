from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
import logging

from app.core.database import check_connection
from app.api.kpi_router import router as kpi_router
from app.agent.router import router as agent_router
from app.events.events_router import router as events_router
from app.ml.ml_router import router as ml_router
from app.geo.geo_router import router as geo_router
from app.events.events_service import refresh_events


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if check_connection():
        logger.info("✅ PostgreSQL connecté")
    else:
        logger.warning("⚠️  PostgreSQL non disponible")
    try:
        result = refresh_events()
        logger.info(f"✅ Événements initialisés : {result['detected']} détectés")
    except Exception as e:
        logger.warning(f"⚠️  Événements non initialisés : {e}")
    yield
    logger.info("🛑 InsureDecide API arrêtée")


app = FastAPI(
    title="InsureDecide API",
    description="Plateforme d'aide à la décision stratégique — Assurance Tunisie",
    version="6.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics sur /metrics
Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_respect_env_var=False,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics", "/health"],
    inprogress_name="insuredecide_requests_inprogress",
    inprogress_labels=True,
).instrument(app).expose(app)

app.include_router(kpi_router)
app.include_router(agent_router)
app.include_router(events_router)
app.include_router(ml_router)
app.include_router(geo_router)
from app.routers.client360_router import router as denodo_router
app.include_router(denodo_router, prefix="/api/denodo", tags=["Denodo"])


@app.get("/", tags=["Santé"])
def root():
    return {
        "message": "InsureDecide API v6.0 🚀",
        "modules": ["KPIs", "Agent IA", "Événements WS", "MLOps SHAP", "Géographie", "Prometheus"]
    }


@app.get("/health", tags=["Santé"])
def health():
    from app.events.ws_manager import manager
    return {
        "status":        "healthy" if check_connection() else "degraded",
        "database":      "connected" if check_connection() else "disconnected",
        "ws_connexions": manager.connection_count(),
    }