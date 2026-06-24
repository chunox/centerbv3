from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.middleware.rate_limit import AuthRateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — nada que seedear: packs son estáticos en código
    yield
    # Shutdown


app = FastAPI(
    title="Center MVP1",
    version="1.0.0",
    description="Center — Project management API",
    docs_url="/docs" if settings.is_dev else None,
    redoc_url="/redoc" if settings.is_dev else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthRateLimitMiddleware)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}
