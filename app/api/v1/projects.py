from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_actor_id
from app.database import get_db
from app.models.entities import Project, ProjectMember, ProjectRole, User
from app.schemas.access_context import AccessContextResponse
from app.schemas.projects import ProjectResponse
from app.services.access_context import build_access_context
from app.services.access import require_capability, require_project_member
from app.services.audit import write_audit

router = APIRouter()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == str(project_id)).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    return project


# ─── Schemas ─────────────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    nombre: str
    pack_slug: str
    template_slug: str
    delivery_mode: str
    descripcion: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None


class UpdateProjectRequest(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None


class ProjectSettingsRequest(BaseModel):
    effort_unit: str | None = None
    hours_per_story_point: float | None = None


class AddProjectMemberRequest(BaseModel):
    user_id: str | None = None
    email: str | None = None     # alternativa a user_id: busca por email
    role_slug: str


class ProjectMemberResponse(BaseModel):
    membership_id: str
    user_id: str
    nombre: str
    email: str
    avatar_url: str | None
    role_id: str
    role_name: str
    role_slug: str
    joined_at: datetime

    model_config = {"from_attributes": True}


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """Detalle básico de un proyecto."""
    project = get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    return ProjectResponse(
        id=project.id,
        org_id=project.organization_id,
        name=project.nombre,
        description=project.descripcion,
        pack_slug=project.pack_slug,
        template_slug=project.template_slug,
        delivery_mode=project.delivery_mode,
        estado=project.estado,
        fecha_inicio=project.fecha_inicio,
        fecha_fin=project.fecha_fin,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("/{project_id}/access-context", response_model=AccessContextResponse)
def access_context(
    project_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """
    Bundle de runtime para el frontend.
    Capabilities, workbenches, entity_types, workflows según (pack, template, rol del actor).
    Solo accesible para miembros del proyecto.
    """
    project = get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    return build_access_context(db, project, actor_id)


@router.get("/{project_id}/members", response_model=list[ProjectMemberResponse])
def list_project_members(
    project_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """Lista miembros del proyecto con su rol."""
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    rows = (
        db.query(ProjectMember, User, ProjectRole)
        .join(User, User.id == ProjectMember.user_id)
        .join(ProjectRole, ProjectRole.id == ProjectMember.role_id)
        .filter(ProjectMember.project_id == str(project_id))
        .order_by(User.nombre)
        .all()
    )
    return [
        ProjectMemberResponse(
            membership_id=m.id,
            user_id=u.id,
            nombre=u.nombre,
            email=u.email,
            avatar_url=u.avatar_url,
            role_id=r.id,
            role_name=r.nombre,
            role_slug=r.slug,
            joined_at=m.joined_at,
        )
        for m, u, r in rows
    ]


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    body: UpdateProjectRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """Actualiza nombre, descripción y fechas del proyecto."""
    project = get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "workbench.settings")
    if body.nombre is not None:
        project.nombre = body.nombre
    if body.descripcion is not None:
        project.descripcion = body.descripcion
    if body.fecha_inicio is not None:
        project.fecha_inicio = body.fecha_inicio
    if body.fecha_fin is not None:
        project.fecha_fin = body.fecha_fin
    db.commit()
    db.refresh(project)
    return ProjectResponse(
        id=project.id, org_id=project.organization_id, name=project.nombre,
        description=project.descripcion, pack_slug=project.pack_slug,
        template_slug=project.template_slug, delivery_mode=project.delivery_mode,
        estado=project.estado, fecha_inicio=project.fecha_inicio,
        fecha_fin=project.fecha_fin, created_at=project.created_at, updated_at=project.updated_at,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_project(
    project_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """Soft delete: marca el proyecto como archivado."""
    project = get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    if ctx.role_slug != "pm":
        raise HTTPException(status_code=403, detail="Solo el PM puede archivar el proyecto")
    project.estado = "archivado"
    db.commit()


@router.get("/{project_id}/settings")
def get_project_settings(
    project_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    project = get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    return project.settings or {}


@router.patch("/{project_id}/settings")
def update_project_settings(
    project_id: str,
    body: ProjectSettingsRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    project = get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "workbench.settings")
    current = dict(project.settings or {})
    if body.effort_unit is not None:
        current["effort_unit"] = body.effort_unit
    if body.hours_per_story_point is not None:
        current["hours_per_story_point"] = body.hours_per_story_point
    project.settings = current
    write_audit(
        db, project=project, actor_id=actor_id,
        entity_type="project", entity_id=str(project.id), action="settings_updated",
        changes={"settings": current},
    )
    db.commit()
    db.refresh(project)
    return project.settings


@router.post("/{project_id}/members", response_model=ProjectMemberResponse, status_code=status.HTTP_201_CREATED)
def add_project_member(
    project_id: str,
    body: AddProjectMemberRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    project = get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "member.add")
    # Resolver usuario por user_id o email
    if body.email:
        user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    elif body.user_id:
        user = db.query(User).filter(User.id == body.user_id).first()
    else:
        raise HTTPException(status_code=422, detail="Se requiere user_id o email")
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    role = db.query(ProjectRole).filter(
        ProjectRole.project_id == str(project_id),
        ProjectRole.slug == body.role_slug,
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail=f"Rol '{body.role_slug}' no existe en este proyecto")
    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == str(project_id),
        ProjectMember.user_id == user.id,
        ProjectMember.role_id == role.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="El usuario ya es miembro con este rol")
    member = ProjectMember(project_id=str(project_id), user_id=user.id, role_id=role.id)
    db.add(member)
    write_audit(
        db, project=project, actor_id=actor_id,
        entity_type="member", entity_id=str(user.id), action="member_added",
        changes={"email": user.email, "role_slug": body.role_slug},
    )
    db.commit()
    db.refresh(member)
    return ProjectMemberResponse(
        membership_id=member.id, user_id=user.id, nombre=user.nombre,
        email=user.email, avatar_url=user.avatar_url,
        role_id=role.id, role_name=role.nombre, role_slug=role.slug,
        joined_at=member.joined_at,
    )


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_member(
    project_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "member.remove")
    project = get_project_or_404(db, project_id)
    if user_id == actor_id:
        raise HTTPException(status_code=400, detail="No podés removerte a vos mismo")
    members = db.query(ProjectMember).filter(
        ProjectMember.project_id == str(project_id),
        ProjectMember.user_id == user_id,
    ).all()
    if not members:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")
    for m in members:
        write_audit(
            db, project=project, actor_id=actor_id,
            entity_type="member", entity_id=str(user_id), action="member_removed",
            changes={"membership_id": str(m.id)},
        )
        db.delete(m)
    db.commit()
