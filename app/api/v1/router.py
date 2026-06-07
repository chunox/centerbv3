from fastapi import APIRouter

from app.api.v1 import attachments, comments, jobs, projects, transitions, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(users.router)
api_router.include_router(jobs.router)
api_router.include_router(projects.router)
api_router.include_router(comments.router)
api_router.include_router(attachments.router)
api_router.include_router(transitions.router)
