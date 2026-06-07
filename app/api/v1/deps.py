from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Feature, Milestone, Project


def get_project_or_404(project_id: UUID, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return project


def get_milestone_or_404(
    project_id: UUID, milestone_id: UUID, db: Session
) -> Milestone:
    get_project_or_404(project_id, db)
    milestone = db.get(Milestone, milestone_id)
    if not milestone or milestone.project_id != project_id:
        raise HTTPException(status_code=404, detail="Milestone no encontrado")
    return milestone


def get_feature_or_404(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    db: Session,
) -> Feature:
    get_milestone_or_404(project_id, milestone_id, db)
    feature = db.get(Feature, feature_id)
    if not feature or feature.milestone_id != milestone_id:
        raise HTTPException(status_code=404, detail="Feature no encontrada")
    if feature.project_id != project_id:
        raise HTTPException(status_code=404, detail="Feature no encontrada")
    return feature
