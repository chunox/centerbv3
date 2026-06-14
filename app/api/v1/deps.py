from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord


def get_project_or_404(project_id: UUID, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return project


def _get_typed_record(
    db: Session,
    record_id: UUID,
    *,
    project_id: UUID | None = None,
    entity_type: str,
    parent_id: UUID | None = None,
) -> ProjectRecord:
    row = db.get(ProjectRecord, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{entity_type} no encontrado")
    if row.record_type != entity_type:
        raise HTTPException(status_code=404, detail=f"{entity_type} no encontrado")
    if project_id is not None and row.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"{entity_type} no encontrado")
    if parent_id is not None and row.parent_id != parent_id:
        raise HTTPException(status_code=404, detail=f"{entity_type} no encontrado")
    return row


def get_milestone_or_404(
    project_id: UUID, milestone_id: UUID, db: Session
) -> ProjectRecord:
    get_project_or_404(project_id, db)
    return _get_typed_record(
        db, milestone_id, project_id=project_id, entity_type="milestone"
    )


def get_feature_or_404(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    db: Session,
) -> ProjectRecord:
    get_milestone_or_404(project_id, milestone_id, db)
    return _get_typed_record(
        db,
        feature_id,
        project_id=project_id,
        entity_type="feature",
        parent_id=milestone_id,
    )


def get_task_or_404(
    project_id: UUID,
    feature_id: UUID,
    task_id: UUID,
    db: Session,
) -> ProjectRecord:
    row = _get_typed_record(
        db, task_id, project_id=project_id, entity_type="task", parent_id=feature_id
    )
    return row
