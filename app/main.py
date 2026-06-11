"""
Aplicación FastAPI — Center v3 backend.

Arranque:
- Migraciones Alembic al importar (database_migrations)
- Scheduler de jobs (sync estados de hitos)
- CORS según settings.cors_origin_list (frontend Vite en :5173)

API REST bajo /api/v1. Health en /health.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text

from app.api.v1.router import api_router
from app.config import settings
from app.database import engine
from app.database_migrations import run_migrations
from app.scheduler import shutdown_scheduler, start_scheduler
from app.schemas.health import HealthResponse

run_migrations()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.database import SessionLocal
    from app.services.packs import ensure_system_packs

    with SessionLocal() as db:
        ensure_system_packs(db)
        db.commit()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="Proyecto Central API v3",
    description="Backend v3 — FastAPI, SQLAlchemy, SQLite/PostgreSQL",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", response_model=HealthResponse)
def health():
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    status = "ok" if db_status == "ok" else "degraded"
    return HealthResponse(status=status, version="3.0.0", database=db_status)


@app.get("/")
def root():
    return {"root": True, "version": "3.0.0"}
