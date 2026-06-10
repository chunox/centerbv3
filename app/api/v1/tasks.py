from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.v1.deps import get_feature_or_404, get_project_or_404
from app.database import get_db
from app.models.entities import Task, TaskDependency, User
from app.schemas.task_dependencies import (
    TaskDependencyCreate,
    TaskDependencyDelete,
    TaskDependencyRead,
)
from app.schemas.tasks import TaskCreate, TaskMove, TaskRead, TaskSubtaskCreate, TaskUpdate
from app.domain.capabilities import KANBAN_TASK_CREATE
from app.services.access import assert_not_pm_for_task_ops, assert_project_active
from app.services.workflow.authorize import assert_capability
from app.services.features import sync_feature_from_tasks
from app.services.task_dependencies import create_dependency, delete_dependency
from app.services.tasks import create_subtask, move_task, sync_task_assignees, update_task

router = APIRouter(tags=["tasks"])


def _reload_task(db: Session, task_id: UUID) -> Task:
    task = db.scalar(
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.task_assignees))
    )
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return task


def _validate_users(payload: TaskCreate, db: Session) -> None:
    creator = db.get(User, payload.created_by)
    if not creator:
        raise HTTPException(status_code=404, detail="Usuario creador no encontrado")
    for user_id in payload.asignado_ids:
        if not db.get(User, user_id):
            raise HTTPException(
                status_code=404,
                detail=f"Usuario asignado no encontrado: {user_id}",
            )


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
        .options(selectinload(Task.task_assignees))
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
    assert_capability(db, project.id, payload.created_by, KANBAN_TASK_CREATE)

    data = payload.model_dump(exclude={"asignado_ids"})
    task = Task(
        feature_id=feature_id,
        project_id=feature.project_id,
        **data,
    )
    db.add(task)
    db.flush()

    if payload.asignado_ids:
        sync_task_assignees(
            db,
            task,
            project,
            actor_user_id=payload.created_by,
            user_ids=payload.asignado_ids,
        )

    sync_feature_from_tasks(
        db, feature, project, actor_user_id=payload.created_by
    )
    db.commit()
    return _reload_task(db, task.id)


@router.post(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/tasks/{task_id}/subtasks",
    response_model=TaskRead,
    status_code=201,
)
def create_task_subtask(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    task_id: UUID,
    payload: TaskSubtaskCreate,
    db: Session = Depends(get_db),
):
    feature = get_feature_or_404(project_id, milestone_id, feature_id, db)
    project = get_project_or_404(project_id, db)
    parent = db.get(Task, task_id)
    if not parent or parent.feature_id != feature_id:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    child = create_subtask(db, parent, feature, project, payload)
    db.commit()
    return _reload_task(db, child.id)


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
    return _reload_task(db, task.id)


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
    task = _reload_task(db, task_id)
    if task.feature_id != feature_id:
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
    task = db.scalar(
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.task_assignees))
    )
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
    return _reload_task(db, task.id)


@router.post(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/tasks/{task_id}/dependencies",
    response_model=TaskDependencyRead,
    status_code=201,
)
def add_task_dependency(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    task_id: UUID,
    payload: TaskDependencyCreate,
    db: Session = Depends(get_db),
):
    feature = get_feature_or_404(project_id, milestone_id, feature_id, db)
    project = get_project_or_404(project_id, db)
    successor = db.get(Task, task_id)
    if not successor or successor.feature_id != feature_id:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    predecessor = db.get(Task, payload.depends_on_task_id)
    if not predecessor or predecessor.project_id != project.id:
        raise HTTPException(
            status_code=404, detail="Tarea predecesora no encontrada"
        )

    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    dep = create_dependency(
        db,
        project,
        successor,
        predecessor,
        actor_user_id=payload.actor_user_id,
    )
    db.commit()
    db.refresh(dep)
    return dep


@router.delete(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/tasks/{task_id}/dependencies/{dep_id}",
    status_code=204,
)
def remove_task_dependency(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    task_id: UUID,
    dep_id: UUID,
    payload: TaskDependencyDelete = Body(),
    db: Session = Depends(get_db),
):
    get_feature_or_404(project_id, milestone_id, feature_id, db)
    project = get_project_or_404(project_id, db)
    task = db.get(Task, task_id)
    if not task or task.feature_id != feature_id:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    dep = db.get(TaskDependency, dep_id)
    if not dep or dep.task_id != task_id:
        raise HTTPException(status_code=404, detail="Dependencia no encontrada")

    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    delete_dependency(db, project, dep, actor_user_id=payload.actor_user_id)
    db.commit()
