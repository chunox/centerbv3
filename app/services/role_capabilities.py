"""Merge de capabilities en roles (incluye roles sistema)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRole, ProjectRoleCapability

PRIMARY_ADMIN_ROLE_SLUGS = ("owner", "coordinador", "pm", "pm_tecnico")


def ensure_role_capabilities(
    db: Session,
    project_id: uuid.UUID,
    role_slug: str,
    capabilities: list[str],
) -> list[str]:
    """Agrega capabilities faltantes al rol (idempotente). Devuelve las recién agregadas."""
    role = db.scalar(
        select(ProjectRole).where(
            ProjectRole.project_id == project_id,
            ProjectRole.slug == role_slug,
        )
    )
    if role is None:
        return []
    return ensure_role_capabilities_for_role(db, role, capabilities)


def ensure_role_capabilities_for_role(
    db: Session,
    role: ProjectRole,
    capabilities: list[str],
) -> list[str]:
    existing = set(
        db.scalars(
            select(ProjectRoleCapability.capability_key).where(
                ProjectRoleCapability.role_id == role.id
            )
        )
    )
    added: list[str] = []
    for cap in capabilities:
        if cap and cap not in existing:
            db.add(ProjectRoleCapability(role_id=role.id, capability_key=cap))
            existing.add(cap)
            added.append(cap)
    if added:
        db.flush()
    return added


def primary_admin_role(roles: list[ProjectRole]) -> ProjectRole | None:
    by_slug = {r.slug: r for r in roles}
    for slug in PRIMARY_ADMIN_ROLE_SLUGS:
        if slug in by_slug:
            return by_slug[slug]
    return roles[0] if roles else None


def sync_workflow_transition_capabilities(
    db: Session,
    project: Project,
    definition: dict[str, Any],
) -> list[str]:
    """Asigna required_capabilities de transiciones a roles según allowed_role_slugs o admin primario."""
    from app.services.project_roles import list_project_roles

    roles = list_project_roles(db, project.id)
    by_slug = {r.slug: r for r in roles}
    admin = primary_admin_role(roles)
    added: list[str] = []

    for transition in definition.get("transitions") or []:
        if transition.get("enabled") is False:
            continue
        caps = [c for c in (transition.get("required_capabilities") or []) if c]
        if not caps:
            continue

        if "allowed_role_slugs" in transition:
            allowed_slugs = [s for s in (transition.get("allowed_role_slugs") or []) if s]
            target_roles = [by_slug[s] for s in allowed_slugs if s in by_slug]
        elif admin is not None:
            target_roles = [admin]
        else:
            target_roles = []

        for role in target_roles:
            for cap in caps:
                added.extend(ensure_role_capabilities_for_role(db, role, [cap]))

    return list(dict.fromkeys(added))
