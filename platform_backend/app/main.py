from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import settings
import app.db.base  # noqa: F401 — registers all models with SQLAlchemy mapper
from app.api.routes import (
    auth,
    profile,
    assessment,
    collaboration,
    personality,
    candidates,
    blueprints,
)

# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Static uploads (avatars, resumes) ─────────────────────────
uploads_root = Path(settings.upload_dir).resolve().parent
uploads_root.mkdir(parents=True, exist_ok=True)
Path(settings.avatar_dir).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_root)), name="uploads")

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────
app.include_router(auth.router,          prefix="/api/v1")
app.include_router(profile.router,       prefix="/api/v1")
app.include_router(assessment.router,    prefix="/api/v1")
app.include_router(collaboration.router, prefix="/api/v1")
app.include_router(personality.router,   prefix="/api/v1")
app.include_router(candidates.router,    prefix="/api/v1")
app.include_router(blueprints.router,    prefix="/api/v1")

# ── Health check ──────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "version": settings.app_version}
