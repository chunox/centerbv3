"""
Capa de autorización — membresía de proyecto y capabilities.
Todos los endpoints de proyecto deben llamar a require_project_member()
para garantizar que el actor pertenece al proyecto antes de operar.
"""
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domain.packs.definitions import TEMPLATE_TO_PACK, get_pack
from app.models.entities import Project, ProjectMember, ProjectRole

ROLE_PRIORITY: tuple[str, ...] = ("pm", "tech_lead", "dev", "qa", "cliente")


@dataclass
class MemberContext:
    actor_id: str
    project_id: str
    role_slug: str
    role_id: str
    capabilities: set[str] = field(default_factory=set)
    role_slugs: set[str] = field(default_factory=set)


def _resolve_capabilities(project: Project, role_slug: str) -> set[str]:
    """Resuelve las capabilities del rol en el pack del proyecto."""
    pack_key = TEMPLATE_TO_PACK.get(str(project.template_slug), str(project.pack_slug))
    pack = get_pack(pack_key)
    if not pack:
        return set()
    return set(pack.capabilities_by_role.get(role_slug, ()))


def _primary_role_slug(role_slugs: set[str]) -> str:
    for slug in ROLE_PRIORITY:
        if slug in role_slugs:
            return slug
    return next(iter(role_slugs))


def get_member_contexts(db: Session, actor_id: str, project_id: str) -> list[MemberContext]:
    """Todas las membresías del actor en el proyecto (multi-rol)."""
    rows = (
        db.query(ProjectMember, ProjectRole, Project)
        .join(ProjectRole, ProjectRole.id == ProjectMember.role_id)
        .join(Project, Project.id == ProjectMember.project_id)
        .filter(
            ProjectMember.project_id == str(project_id),
            ProjectMember.user_id == str(actor_id),
        )
        .all()
    )
    contexts: list[MemberContext] = []
    for member, role, project in rows:
        caps = _resolve_capabilities(project, role.slug)
        contexts.append(
            MemberContext(
                actor_id=actor_id,
                project_id=str(project_id),
                role_slug=role.slug,
                role_id=role.id,
                capabilities=caps,
                role_slugs={role.slug},
            )
        )
    return contexts


def get_member_context(db: Session, actor_id: str, project_id: str) -> MemberContext | None:
    """Contexto fusionado: unión de capabilities de todos los roles del actor."""
    contexts = get_member_contexts(db, actor_id, project_id)
    if not contexts:
        return None
    all_caps: set[str] = set()
    all_roles: set[str] = set()
    for ctx in contexts:
        all_caps |= ctx.capabilities
        all_roles |= ctx.role_slugs
    primary = _primary_role_slug(all_roles)
    primary_ctx = next(c for c in contexts if c.role_slug == primary)
    return MemberContext(
        actor_id=actor_id,
        project_id=str(project_id),
        role_slug=primary,
        role_id=primary_ctx.role_id,
        capabilities=all_caps,
        role_slugs=all_roles,
    )


def require_project_member(db: Session, actor_id: str, project_id: str) -> MemberContext:
    """
    Lanza 403 si el actor no es miembro del proyecto.
    Uso en endpoints: ctx = require_project_member(db, actor_id, project_id)
    """
    ctx = get_member_context(db, actor_id, project_id)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenés acceso a este proyecto",
        )
    return ctx


def require_capability(ctx: MemberContext, capability: str) -> None:
    """Lanza 403 si el actor no tiene la capability requerida."""
    if capability not in ctx.capabilities:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Sin permiso: {capability}",
        )


def require_any_capability(ctx: MemberContext, *capabilities: str) -> None:
    """Lanza 403 si el actor no tiene ninguna de las capabilities."""
    if not capabilities:
        return
    if not any(c in ctx.capabilities for c in capabilities):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Sin permiso: se requiere alguna de {', '.join(capabilities)}",
        )


def require_role(ctx: MemberContext, *roles: str) -> None:
    """Lanza 403 si el actor no tiene ninguno de los roles requeridos."""
    if not ctx.role_slugs.intersection(roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Rol requerido: {', '.join(roles)}",
        )
