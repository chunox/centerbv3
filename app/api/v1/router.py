from fastapi import APIRouter

from app.api.v1 import auth, organizations, projects, members, records, blockers, sprints, ceremonies, hub, comments, attachments, activity, view_preferences

api_router = APIRouter()

api_router.include_router(auth.router,             prefix="/auth",         tags=["auth"])
api_router.include_router(organizations.router,    prefix="/organizations", tags=["organizations"])
api_router.include_router(projects.router,         prefix="/projects",     tags=["projects"])
api_router.include_router(members.router,          prefix="/users",        tags=["users"])
api_router.include_router(records.router,          prefix="/projects",     tags=["records"])
api_router.include_router(blockers.router,         prefix="/projects",     tags=["blockers"])
api_router.include_router(sprints.router,          prefix="/projects",     tags=["sprints"])
api_router.include_router(ceremonies.router,       prefix="/projects",     tags=["ceremonies"])
api_router.include_router(hub.router,              prefix="/projects",     tags=["hub"])
api_router.include_router(comments.router,         prefix="/projects",     tags=["comments"])
api_router.include_router(attachments.router,      prefix="/projects",     tags=["attachments"])
api_router.include_router(activity.router,         prefix="/projects",     tags=["activity"])
api_router.include_router(view_preferences.router, prefix="/projects",     tags=["view_preferences"])
