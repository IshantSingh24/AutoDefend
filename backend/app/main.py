import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.init_db import init_db
from app.api.webhooks import router as webhook_router

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("AutoDefend starting up | env=%s", settings.app_env)
    logger.info(
        "Config | confidence_threshold=%.2f | mock_apis=%s",
        settings.auto_defend_confidence_threshold,
        settings.use_mock_apis,
    )
    # Create DB tables on startup (idempotent)
    init_db()
    yield
    logger.info("AutoDefend shutting down")


app = FastAPI(
    title="AutoDefend",
    description=(
        "Agentic AI system for autonomous payment dispute defense. "
        "Assembles evidence, evaluates winability, and submits bank-compliant "
        "rebuttals — or recommends acceptance when evidence is insufficient."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────
app.include_router(webhook_router, prefix="/webhook", tags=["Webhooks"])

# Future routers (added as steps complete):
# from app.api.dashboard import router as dashboard_router
# app.include_router(dashboard_router, prefix="/api", tags=["Dashboard"])


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe — confirms the service is running."""
    return {
        "status":    "ok",
        "version":   app.version,
        "env":       settings.app_env,
        "mock_mode": settings.use_mock_apis,
    }
