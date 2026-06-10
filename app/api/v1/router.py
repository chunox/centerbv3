"""Agregador de routers v1. Orden: auth/org antes que dominio de proyecto."""
from fastapi import APIRouter

from app.api.v1 import (
    attachments,
    auth,
    comments,
    jobs,
    organizations,
    project_access,
    project_templates,
    projects,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(users.router)
api_router.include_router(jobs.router)
api_router.include_router(project_templates.router)
api_router.include_router(projects.router)
api_router.include_router(project_access.router)
api_router.include_router(comments.router)
api_router.include_router(attachments.router)
