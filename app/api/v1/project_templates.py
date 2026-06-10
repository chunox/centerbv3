"""Catálogo de templates de proyecto."""
from fastapi import APIRouter

from app.domain.project_templates import list_templates_for_api
from app.schemas.projects import ProjectTemplateRead

router = APIRouter(prefix="/project-templates", tags=["project-templates"])


@router.get("", response_model=list[ProjectTemplateRead])
def list_project_templates():
    return list_templates_for_api()
