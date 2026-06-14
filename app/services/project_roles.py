"""CRUD de roles, capacidades y seed de acceso por proyecto."""
from __future__ import annotations

import json
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.capabilities import (
    TEMPLATE_ROLE_CAPABILITIES,
    TEMPLATE_ROLE_LABELS,
    validate_capability_keys,
)
from app.domain.project_templates import (
    DEFAULT_TEMPLATE_SLUG,
    get_template,
    template_slug_for_legacy_tipo,
)
from app.domain.workbenches import DEFAULT_WORKBENCHES
from app.domain.workflow_templates import workflow_for_profile
from app.models.entities import (
    Project,
    ProjectMember,
    ProjectRole,
    ProjectRoleCapability,
    ProjectWorkbenchDefinition,
    ProjectWorkflowDefinition,
)


def seed_project_from_template(
    db: Session,
    project: Project,
    template_slug: str,
) -> dict[str, ProjectRole]:
    """Crea roles del template, workflows y workbenches. Devuelve mapa slug → role."""
    project.pack_slug = getattr(project, "pack_slug", None) or "software"
    tpl = get_template(template_slug)
    created: dict[str, ProjectRole] = {}
    for orden, slug in enumerate(tpl.roles, start=1):
        nombre = TEMPLATE_ROLE_LABELS.get(slug, slug)
        role = ProjectRole(
            project_id=project.id,
            slug=slug,
            nombre=nombre,
            is_system=True,
            orden=orden,
        )
        db.add(role)
        db.flush()
        for cap in TEMPLATE_ROLE_CAPABILITIES.get(slug, frozenset()):
            db.add(ProjectRoleCapability(role_id=role.id, capability_key=cap))
        created[slug] = role

    for entity_type in ("feature", "task", "query", "report", "milestone"):
        profile = getattr(project, "profile_slug", None) or "with_client"
        wf = workflow_for_profile(profile, entity_type)
        db.add(
            ProjectWorkflowDefinition(
                project_id=project.id,
                entity_type=entity_type,
                version=1,
                is_active=True,
                definition=json.dumps(wf, ensure_ascii=False),
            )
        )
    db.add(
        ProjectWorkbenchDefinition(
            project_id=project.id,
            definition=json.dumps(DEFAULT_WORKBENCHES, ensure_ascii=False),
        )
    )
    from app.domain.packs.catalog import pack_software_manifest
    from app.services.packs import _seed_record_types_from_manifest

    _seed_record_types_from_manifest(db, project, pack_software_manifest())
    return created


def seed_default_project_access(db: Session, project: Project) -> dict[str, ProjectRole]:
    """Compat: seed según template_slug del proyecto o tipo legacy."""
    from app.services.project_profile import legacy_tipo_for_project

    slug = getattr(project, "template_slug", None) or template_slug_for_legacy_tipo(
        legacy_tipo_for_project(project)
    )
    return seed_project_from_template(db, project, slug or DEFAULT_TEMPLATE_SLUG)


def list_project_roles(db: Session, project_id: uuid.UUID) -> list[ProjectRole]:
    return list(
        db.scalars(
            select(ProjectRole)
            .where(ProjectRole.project_id == project_id)
            .order_by(ProjectRole.orden.asc(), ProjectRole.nombre.asc())
        )
    )


def get_role_capabilities(db: Session, role_id: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            select(ProjectRoleCapability.capability_key).where(
                ProjectRoleCapability.role_id == role_id
            )
        )
    )


def create_custom_role(
    db: Session,
    project: Project,
    *,
    slug: str,
    nombre: str,
    capability_keys: list[str],
    descripcion: str | None = None,
    color: str | None = None,
) -> ProjectRole:
    invalid = validate_capability_keys(capability_keys)
    if invalid:
        raise HTTPException(status_code=422, detail=f"Capacidades inválidas: {invalid}")
    existing = db.scalar(
        select(ProjectRole.id).where(
            ProjectRole.project_id == project.id, ProjectRole.slug == slug
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Ya existe rol '{slug}'")

    max_orden = db.scalar(
        select(func.max(ProjectRole.orden)).where(ProjectRole.project_id == project.id)
    ) or 0
    role = ProjectRole(
        project_id=project.id,
        slug=slug,
        nombre=nombre,
        descripcion=descripcion,
        color=color,
        is_system=False,
        orden=int(max_orden) + 1,
    )
    db.add(role)
    db.flush()
    for key in capability_keys:
        db.add(ProjectRoleCapability(role_id=role.id, capability_key=key))
    return role


def update_role_capabilities(
    db: Session,
    role: ProjectRole,
    capability_keys: list[str],
) -> None:
    if role.is_system:
        raise HTTPException(status_code=409, detail="No se pueden editar capacidades de rol sistema")
    invalid = validate_capability_keys(capability_keys)
    if invalid:
        raise HTTPException(status_code=422, detail=f"Capacidades inválidas: {invalid}")
    db.query(ProjectRoleCapability).filter(ProjectRoleCapability.role_id == role.id).delete()
    for key in capability_keys:
        db.add(ProjectRoleCapability(role_id=role.id, capability_key=key))


def delete_custom_role(db: Session, role: ProjectRole) -> None:
    if role.is_system:
        raise HTTPException(status_code=409, detail="No se pueden eliminar roles sistema")
    members = db.scalar(
        select(func.count()).select_from(ProjectMember).where(ProjectMember.role_id == role.id)
    )
    if members:
        raise HTTPException(status_code=409, detail="El rol tiene miembros asignados")
    db.delete(role)


def assign_member_role(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    role_id: uuid.UUID,
) -> ProjectMember:
    role = db.get(ProjectRole, role_id)
    if not role or role.project_id != project_id:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    existing = db.scalar(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.role_id == role_id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="El usuario ya tiene ese rol")
    member = ProjectMember(project_id=project_id, user_id=user_id, role_id=role_id)
    db.add(member)
    return member


def remove_member_role(db: Session, member: ProjectMember) -> None:
    role = db.get(ProjectRole, member.role_id)
    if role and role.slug in ("pm", "pm_tecnico"):
        pm_count = db.scalar(
            select(func.count())
            .select_from(ProjectMember)
            .join(ProjectRole, ProjectRole.id == ProjectMember.role_id)
            .where(
                ProjectMember.project_id == member.project_id,
                ProjectRole.slug.in_(("pm", "pm_tecnico")),
            )
        )
        if pm_count is not None and pm_count <= 1:
            raise HTTPException(status_code=409, detail="Debe quedar al menos un PM")
    db.delete(member)


def _normalize_task_workflow_moves(defn: dict) -> dict:
    from app.services.workflow.engine import normalize_task_workflow_moves

    return normalize_task_workflow_moves(defn)


def update_workflow_definition(
    db: Session,
    project: Project,
    entity_type: str,
    definition: dict,
) -> tuple[ProjectWorkflowDefinition, list[str]]:
    from app.services.role_capabilities import sync_workflow_transition_capabilities

    if entity_type == "task":
        definition = _normalize_task_workflow_moves(definition)

    _validate_workflow_definition(
        definition,
        entity_type=entity_type,
        role_slugs={r.slug for r in list_project_roles(db, project.id)},
    )
    capabilities_added = sync_workflow_transition_capabilities(db, project, definition)
    latest = db.scalar(
        select(func.max(ProjectWorkflowDefinition.version)).where(
            ProjectWorkflowDefinition.project_id == project.id,
            ProjectWorkflowDefinition.entity_type == entity_type,
        )
    ) or 0
    db.execute(
        select(ProjectWorkflowDefinition)
        .where(
            ProjectWorkflowDefinition.project_id == project.id,
            ProjectWorkflowDefinition.entity_type == entity_type,
            ProjectWorkflowDefinition.is_active.is_(True),
        )
    )
    for row in db.scalars(
        select(ProjectWorkflowDefinition).where(
            ProjectWorkflowDefinition.project_id == project.id,
            ProjectWorkflowDefinition.entity_type == entity_type,
            ProjectWorkflowDefinition.is_active.is_(True),
        )
    ):
        row.is_active = False

    wf = ProjectWorkflowDefinition(
        project_id=project.id,
        entity_type=entity_type,
        version=int(latest) + 1,
        is_active=True,
        definition=json.dumps(definition, ensure_ascii=False),
    )
    db.add(wf)
    return wf, capabilities_added


def update_workbench_definition(
    db: Session, project: Project, workbenches: list[dict]
) -> ProjectWorkbenchDefinition:
    row = db.scalar(
        select(ProjectWorkbenchDefinition).where(
            ProjectWorkbenchDefinition.project_id == project.id
        )
    )
    payload = json.dumps(workbenches, ensure_ascii=False)
    if row:
        row.definition = payload
        return row
    row = ProjectWorkbenchDefinition(project_id=project.id, definition=payload)
    db.add(row)
    return row


def _validate_workflow_definition(
    defn: dict,
    *,
    entity_type: str | None = None,
    role_slugs: set[str] | None = None,
) -> None:
    from app.services.workflow.categories import validate_task_state_categories

    states = defn.get("states", [])
    if not states:
        raise HTTPException(status_code=422, detail="Workflow sin estados")
    keys = {s["key"] for s in states if isinstance(s, dict) and s.get("key")}
    initial = defn.get("initial_state")
    if initial and initial not in keys:
        raise HTTPException(status_code=422, detail="initial_state inválido")
    if entity_type == "task":
        try:
            validate_task_state_categories(defn)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    for t in defn.get("transitions", []):
        to_state = t.get("to")
        if to_state and to_state != "*" and to_state not in keys:
            raise HTTPException(
                status_code=422,
                detail=f"Transición '{t.get('id')}' apunta a estado inexistente",
            )
        for from_state in t.get("from") or []:
            if from_state not in keys:
                raise HTTPException(
                    status_code=422,
                    detail=f"Transición '{t.get('id')}' parte de estado inexistente: {from_state}",
                )
        if role_slugs is not None:
            for slug in t.get("allowed_role_slugs") or []:
                if slug not in role_slugs:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Rol '{slug}' no existe en el proyecto",
                    )
