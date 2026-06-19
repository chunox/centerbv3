"""
API de proyectos y sub-recursos anidados (hitos, features, inbox, timeline…).

Todas las rutas exigen JWT; el actor se deriva del claim sub.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.auth_deps import get_current_actor_id
from app.api.v1.deps import get_project_or_404
from app.api.v1 import audit_logs as audit_logs_routes
from app.api.v1 import hub_entries as hub_entries_routes
from app.api.v1 import timeline as timeline_routes
from app.database import get_db
from app.models.entities import Organization, Project, ProjectMember, User
from app.services.organizations import (
    list_guest_projects,
    list_org_projects,
    require_org_admin,
    user_has_project_access,
)
from app.domain.capabilities import WORKBENCH_TEAM
from app.schemas.inbox_summary import ProjectInboxSummaryRead
from app.schemas.pm_portfolio import PmPortfolioRead
from app.schemas.portfolio_team_workload import PortfolioTeamWorkloadRead
from app.schemas.team_board import TeamBoardRead
from app.schemas.projects import (
    ProjectCreate,
    ProjectEstadoAction,
    ProjectMemberCreate,
    ProjectMemberRead,
    ProjectMemberUpdate,
    ProjectRead,
    ProjectUpdate,
)
from app.services.inbox_summary import build_inbox_summary
from app.services.pm_portfolio import build_pm_portfolio
from app.services.portfolio_team_workload import build_portfolio_team_workload
from app.services.team_board import build_team_board
from app.services.workflow.authorize import assert_capability
from app.services.deletions import delete_project
from app.services.project_members import (
    add_project_member,
    member_to_read,
    remove_project_member,
    update_project_member_role,
)
from app.domain.project_templates import get_template
from app.services.packs import seed_project_from_pack
from app.domain.packs.catalog import get_pack_manifest
from app.services.projects import apply_project_estado_action, update_project

router = APIRouter(prefix="/projects", tags=["projects"])
router.include_router(hub_entries_routes.router)
router.include_router(audit_logs_routes.router)
router.include_router(timeline_routes.router)


@router.get("", response_model=list[ProjectRead])
def list_projects(
    organization_id: UUID | None = Query(
        default=None,
        description="Proyectos de la organización activa",
    ),
    guest: bool = Query(
        default=False,
        description="Proyectos invitados (project_member sin organization_member)",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    if guest:
        projects = list_guest_projects(db, actor_user_id)
        return projects[offset : offset + limit]

    if organization_id is not None:
        projects = list_org_projects(db, organization_id, actor_user_id)
        return projects[offset : offset + limit]

    stmt = select(Project).order_by(Project.created_at.desc())
    stmt = (
        stmt.join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == actor_user_id)
        .distinct()
    )
    stmt = stmt.offset(offset).limit(limit)
    return list(db.scalars(stmt))


@router.get("/pm-portfolio", response_model=PmPortfolioRead)
def get_pm_portfolio(
    organization_id: UUID,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    return build_pm_portfolio(db, organization_id, actor_user_id)


@router.get("/pm-portfolio/team-workload", response_model=PortfolioTeamWorkloadRead)
def get_pm_portfolio_team_workload(
    organization_id: UUID,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    return build_portfolio_team_workload(db, organization_id, actor_user_id)


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(
    payload: ProjectCreate,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    creator = db.get(User, actor_user_id)
    if not creator:
        raise HTTPException(status_code=404, detail="Usuario creador no encontrado")

    org = db.get(Organization, payload.organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organización no encontrada")
    require_org_admin(db, payload.organization_id, actor_user_id)

    pack_slug = payload.pack_slug or "software"
    if pack_slug == "software":
        template_slug = payload.template_slug or "t1_cliente_clasico"
        tpl = get_template(template_slug)
    else:
        template_slug = payload.template_slug or "t5_freestyle"
        tpl = get_template(template_slug)
    fields = payload.model_dump(
        exclude={"template_slug", "tipo", "pack_slug", "project_structure"}
    )
    project_structure = payload.project_structure
    project = Project(
        **fields,
        template_slug=template_slug,
        pack_slug=pack_slug,
        created_by=actor_user_id,
    )
    db.add(project)
    db.flush()

    try:
        roles = seed_project_from_pack(
            db,
            project,
            pack_slug,
            template_slug=template_slug,
            project_structure=project_structure,
            initial_created_by=actor_user_id if project_structure else None,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    manifest = get_pack_manifest(pack_slug)
    creator_key = tpl.creator_role if pack_slug == "software" else (
        manifest.roles[0].slug if manifest and manifest.roles else "owner"
    )
    creator_role = roles.get(creator_key)
    if not creator_role:
        raise HTTPException(
            status_code=500,
            detail=f"Pack sin rol creador: {creator_key}",
        )
    db.add(
        ProjectMember(
            project_id=project.id,
            user_id=actor_user_id,
            role_id=creator_role.id,
        )
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: UUID,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    if not user_has_project_access(db, project, actor_user_id):
        raise HTTPException(status_code=403, detail="Sin acceso al proyecto")
    return project


@router.get("/{project_id}/inbox-summary", response_model=ProjectInboxSummaryRead)
def get_project_inbox_summary(
    project_id: UUID,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    return build_inbox_summary(db, project, viewer_user_id=actor_user_id)


@router.get("/{project_id}/team-board", response_model=TeamBoardRead)
def get_project_team_board(
    project_id: UUID,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    if not user_has_project_access(db, project, actor_user_id):
        raise HTTPException(status_code=403, detail="Sin acceso al proyecto")
    assert_capability(db, project.id, actor_user_id, WORKBENCH_TEAM)
    return build_team_board(db, project)


@router.patch("/{project_id}", response_model=ProjectRead)
def patch_project(
    project_id: UUID,
    payload: ProjectUpdate,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    update_project(db, project, payload, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def remove_project(
    project_id: UUID,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    delete_project(db, project, actor_user_id=actor_user_id)
    db.commit()


@router.post("/{project_id}/actions", response_model=ProjectRead)
def perform_project_action(
    project_id: UUID,
    payload: ProjectEstadoAction,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    apply_project_estado_action(
        db,
        project,
        action=payload.action,
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}/members", response_model=list[ProjectMemberRead])
def list_project_members(
    project_id: UUID,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    if not user_has_project_access(db, project, actor_user_id):
        raise HTTPException(status_code=403, detail="Sin acceso al proyecto")
    from sqlalchemy.orm import joinedload

    stmt = (
        select(ProjectMember)
        .options(joinedload(ProjectMember.role))
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.joined_at.desc())
    )
    return [member_to_read(m) for m in db.scalars(stmt)]


@router.post(
    "/{project_id}/members", response_model=ProjectMemberRead, status_code=201
)
def add_project_member_endpoint(
    project_id: UUID,
    payload: ProjectMemberCreate,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    try:
        member = add_project_member(
            db, project, payload, actor_user_id=actor_user_id
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ese usuario ya tiene ese rol en el proyecto",
        )
    db.refresh(member)
    return member_to_read(member)


@router.patch(
    "/{project_id}/members/{member_id}",
    response_model=ProjectMemberRead,
)
def patch_project_member(
    project_id: UUID,
    member_id: UUID,
    payload: ProjectMemberUpdate,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    member = db.get(ProjectMember, member_id)
    if not member or member.project_id != project_id:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")

    update_project_member_role(
        db, project, member, payload, actor_user_id=actor_user_id
    )
    db.commit()
    db.refresh(member)
    return member_to_read(member)


@router.delete(
    "/{project_id}/members/{member_id}",
    status_code=204,
)
def delete_project_member(
    project_id: UUID,
    member_id: UUID,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    member = db.get(ProjectMember, member_id)
    if not member or member.project_id != project_id:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")

    remove_project_member(
        db, project, member, actor_user_id=actor_user_id
    )
    db.commit()
