from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.database_migrations import run_migrations
from app.scheduler import shutdown_scheduler, start_scheduler
from app.schemas.health import HealthResponse

run_migrations()


@asynccontextmanager
async def lifespan(_app: FastAPI):
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
    return HealthResponse(status="ok", version="3.0.0")


@app.get("/")
def root():
    return {"root": True, "version": "3.0.0"}
