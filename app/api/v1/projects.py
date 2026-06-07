from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_project_or_404
from app.api.v1 import audit_logs as audit_logs_routes
from app.api.v1 import document_exposures as document_exposures_routes
from app.api.v1 import documents as documents_routes
from app.api.v1 import feature_queries as feature_queries_routes
from app.api.v1 import feature_reports as feature_reports_routes
from app.api.v1 import milestones as milestones_routes
from app.api.v1 import timeline as timeline_routes
from app.database import get_db
from app.models.entities import Project, ProjectMember, User
from app.schemas.projects import (
    ProjectCreate,
    ProjectEstadoAction,
    ProjectMemberCreate,
    ProjectMemberRead,
    ProjectMemberUpdate,
    ProjectRead,
    ProjectUpdate,
)
from app.services.deletions import delete_project
from app.services.project_members import (
    add_project_member,
    remove_project_member,
    update_project_member_role,
)
from app.services.projects import apply_project_estado_action, update_project

router = APIRouter(prefix="/projects", tags=["projects"])
router.include_router(milestones_routes.router)
router.include_router(documents_routes.router)
router.include_router(document_exposures_routes.router)
router.include_router(audit_logs_routes.router)
router.include_router(feature_queries_routes.inbox_router)
router.include_router(feature_reports_routes.inbox_router)
router.include_router(timeline_routes.router)


@router.get("", response_model=list[ProjectRead])
def list_projects(
    user_id: UUID | None = Query(
        default=None,
        description="Filtra proyectos donde el usuario es miembro (demo sin JWT)",
    ),
    db: Session = Depends(get_db),
):
    stmt = select(Project).order_by(Project.created_at.desc())
    if user_id is not None:
        stmt = (
            stmt.join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user_id)
            .distinct()
        )
    return list(db.scalars(stmt))


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    creator = db.get(User, payload.created_by)
    if not creator:
        raise HTTPException(status_code=404, detail="Usuario creador no encontrado")

    project = Project(**payload.model_dump())
    db.add(project)
    db.flush()
    db.add(
        ProjectMember(
            project_id=project.id,
            user_id=payload.created_by,
            rol="pm",
        )
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: UUID, db: Session = Depends(get_db)):
    return get_project_or_404(project_id, db)


@router.patch("/{project_id}", response_model=ProjectRead)
def patch_project(
    project_id: UUID,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    update_project(db, project, payload)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def remove_project(
    project_id: UUID,
    actor_user_id: UUID,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    actor = db.get(User, actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    delete_project(db, project, actor_user_id=actor_user_id)
    db.commit()


@router.post("/{project_id}/actions", response_model=ProjectRead)
def perform_project_action(
    project_id: UUID,
    payload: ProjectEstadoAction,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    apply_project_estado_action(
        db,
        project,
        action=payload.action,
        actor_user_id=payload.actor_user_id,
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}/members", response_model=list[ProjectMemberRead])
def list_project_members(project_id: UUID, db: Session = Depends(get_db)):
    get_project_or_404(project_id, db)
    stmt = (
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.joined_at.desc())
    )
    return list(db.scalars(stmt))


@router.post(
    "/{project_id}/members", response_model=ProjectMemberRead, status_code=201
)
def add_project_member_endpoint(
    project_id: UUID, payload: ProjectMemberCreate, db: Session = Depends(get_db)
):
    project = get_project_or_404(project_id, db)
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    try:
        member = add_project_member(db, project, payload)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ese usuario ya tiene ese rol en el proyecto",
        )
    db.refresh(member)
    return member


@router.patch(
    "/{project_id}/members/{member_id}",
    response_model=ProjectMemberRead,
)
def patch_project_member(
    project_id: UUID,
    member_id: UUID,
    payload: ProjectMemberUpdate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    member = db.get(ProjectMember, member_id)
    if not member or member.project_id != project_id:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")

    update_project_member_role(db, project, member, payload)
    db.commit()
    db.refresh(member)
    return member


@router.delete(
    "/{project_id}/members/{member_id}",
    status_code=204,
)
def delete_project_member(
    project_id: UUID,
    member_id: UUID,
    actor_user_id: UUID,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    actor = db.get(User, actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    member = db.get(ProjectMember, member_id)
    if not member or member.project_id != project_id:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")

    remove_project_member(
        db, project, member, actor_user_id=actor_user_id
    )
    db.commit()
