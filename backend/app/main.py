import logging
from contextlib import asynccontextmanager

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db.init_db import init_db
from app.api.webhooks import router as webhook_router
from app.api.dashboard import router as dashboard_router
from app.api.bulk_auth import router as auth_router
from app.api.demo import router as demo_router

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
app.include_router(auth_router, tags=["Auth"])           # /auth/register, /login, /me, /logout
app.include_router(dashboard_router, prefix="/api", tags=["Dashboard"])
app.include_router(demo_router, prefix="/api", tags=["Demo"])   # /api/demo/simulate (SSE)

# ── Frontend static assets ─────────────────────────────────
# Try multiple candidate paths — works regardless of launch directory
_this_file = os.path.abspath(__file__)                              # .../backend/app/main.py
_app_dir   = os.path.dirname(_this_file)                           # .../backend/app
_backend_dir = os.path.dirname(_app_dir)                           # .../backend
_project_dir = os.path.dirname(_backend_dir)                       # .../RazorPay_hack
_frontend_candidates = [
    os.path.join(_project_dir, "frontend"),                        # standard layout
    os.path.join(_backend_dir, "..", "frontend"),                   # relative fallback
    os.path.join(os.getcwd(), "frontend"),                          # cwd-relative
    os.path.join(os.getcwd(), "..", "frontend"),                    # one level up from cwd
]
frontend_dir = next((p for p in _frontend_candidates if os.path.isdir(p)), None)
logger.info("Frontend dir resolved: %s", frontend_dir)
if frontend_dir and os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    # Public pages
    @app.get("/", include_in_schema=False)
    async def serve_landing():
        return FileResponse(os.path.join(frontend_dir, "landing.html"))

    @app.get("/login", include_in_schema=False)
    async def serve_login():
        return FileResponse(os.path.join(frontend_dir, "login.html"))

    @app.get("/demo", include_in_schema=False)
    async def serve_demo():
        return FileResponse(os.path.join(frontend_dir, "demo.html"))

    # Authenticated console (redirect logic lives in auth.js → /app)
    @app.get("/app", include_in_schema=False)
    async def serve_dashboard():
        return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe — confirms the service is running."""
    return {
        "status":    "ok",
        "version":   app.version,
        "env":       settings.app_env,
        "mock_mode": settings.use_mock_apis,
    }
