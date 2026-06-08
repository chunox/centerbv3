from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_feature_or_404, get_project_or_404
from app.database import get_db
from app.models.entities import Task, User
from app.schemas.tasks import TaskCreate, TaskMove, TaskRead, TaskUpdate
from app.services.access import (
    assert_member_has_role,
    assert_not_pm_for_task_ops,
    assert_project_active,
)
from app.services.features import sync_feature_from_tasks
from app.services.tasks import move_task, update_task

router = APIRouter(tags=["tasks"])


def _validate_users(payload: TaskCreate, db: Session) -> None:
    creator = db.get(User, payload.created_by)
    if not creator:
        raise HTTPException(status_code=404, detail="Usuario creador no encontrado")
    if payload.asignado_a is not None:
        assignee = db.get(User, payload.asignado_a)
        if not assignee:
            raise HTTPException(status_code=404, detail="Usuario asignado no encontrado")


@router.get(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/tasks",
    response_model=list[TaskRead],
)
def list_tasks(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    get_feature_or_404(project_id, milestone_id, feature_id, db)
    stmt = (
        select(Task)
        .where(Task.feature_id == feature_id)
        .order_by(Task.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(stmt))


@router.post(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/tasks",
    response_model=TaskRead,
    status_code=201,
)
def create_task(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    payload: TaskCreate,
    db: Session = Depends(get_db),
):
    feature = get_feature_or_404(project_id, milestone_id, feature_id, db)
    project = get_project_or_404(project_id, db)
    _validate_users(payload, db)
    assert_project_active(project)
    assert_not_pm_for_task_ops(db, project.id, payload.created_by)
    assert_member_has_role(db, project.id, payload.created_by, "dev")

    task = Task(
        feature_id=feature_id,
        project_id=feature.project_id,
        **payload.model_dump(),
    )
    db.add(task)
    db.flush()
    sync_feature_from_tasks(
        db, feature, project, actor_user_id=payload.created_by
    )
    db.commit()
    db.refresh(task)
    return task


@router.patch(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/tasks/{task_id}",
    response_model=TaskRead,
)
def patch_task(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    task_id: UUID,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
):
    feature = get_feature_or_404(project_id, milestone_id, feature_id, db)
    project = get_project_or_404(project_id, db)
    task = db.get(Task, task_id)
    if not task or task.feature_id != feature_id:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    update_task(db, task, feature, project, payload)
    db.commit()
    db.refresh(task)
    return task


@router.get(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/tasks/{task_id}",
    response_model=TaskRead,
)
def get_task(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    task_id: UUID,
    db: Session = Depends(get_db),
):
    get_feature_or_404(project_id, milestone_id, feature_id, db)
    task = db.get(Task, task_id)
    if not task or task.feature_id != feature_id:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return task


@router.patch(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/tasks/{task_id}/move",
    response_model=TaskRead,
)
def move_task_state(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    task_id: UUID,
    payload: TaskMove,
    db: Session = Depends(get_db),
):
    feature = get_feature_or_404(project_id, milestone_id, feature_id, db)
    project = get_project_or_404(project_id, db)
    task = db.get(Task, task_id)
    if not task or task.feature_id != feature_id:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    move_task(
        db,
        task,
        feature,
        project,
        nuevo_estado=payload.estado,
        actor_user_id=payload.actor_user_id,
    )
    db.commit()
    db.refresh(task)
    return task
