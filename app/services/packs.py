"""Seed y aplicación de project packs."""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.packs.catalog import SYSTEM_PACKS, get_pack_manifest
from app.domain.packs.manifest import PackManifest
from app.models.entities import (
    Project,
    ProjectPack,
    ProjectRecordType,
    ProjectRole,
    ProjectRoleCapability,
    ProjectWorkbenchDefinition,
    ProjectWorkflowDefinition,
)
from app.services.project_roles import seed_project_from_template


def _manifest_to_db(manifest: PackManifest) -> str:
    return manifest.model_dump_json()


def ensure_system_packs(db: Session) -> None:
    """Idempotente: inserta packs sistema si faltan."""
    for slug, manifest in SYSTEM_PACKS.items():
        existing = db.scalar(select(ProjectPack.id).where(ProjectPack.slug == slug))
        if existing:
            continue
        db.add(
            ProjectPack(
                slug=slug,
                nombre=manifest.nombre,
                descripcion=manifest.descripcion,
                manifest=_manifest_to_db(manifest),
                is_system=True,
                orden=list(SYSTEM_PACKS.keys()).index(slug),
            )
        )
    db.flush()


def get_project_pack_manifest(db: Session, project: Project) -> PackManifest | None:
    ensure_system_packs(db)
    row = db.scalar(select(ProjectPack).where(ProjectPack.slug == project.pack_slug))
    if row is None:
        return get_pack_manifest(project.pack_slug)
    return PackManifest.model_validate_json(row.manifest)


def list_record_types(db: Session, project_id: uuid.UUID) -> list[ProjectRecordType]:
    return list(
        db.scalars(
            select(ProjectRecordType)
            .where(ProjectRecordType.project_id == project_id)
            .order_by(ProjectRecordType.orden.asc())
        )
    )


def seed_project_from_pack(
    db: Session,
    project: Project,
    pack_slug: str,
    *,
    template_slug: str | None = None,
) -> dict[str, ProjectRole]:
    """Aplica pack al proyecto: record types, roles, workflows, workbenches."""
    manifest = get_pack_manifest(pack_slug)
    if manifest is None:
        raise ValueError(f"Pack desconocido: {pack_slug}")

    project.pack_slug = pack_slug

    if pack_slug == "software":
        tpl = template_slug or manifest.maps_template_slug or project.template_slug
        project.template_slug = tpl
        _seed_record_types_from_manifest(db, project, manifest)
        from app.models.entities import ProjectRole

        roles_list = list(
            db.scalars(select(ProjectRole).where(ProjectRole.project_id == project.id))
        )
        return {r.slug: r for r in roles_list}

    _seed_record_types_from_manifest(db, project, manifest)
    roles = _seed_pack_roles(db, project, manifest)
    _seed_pack_workflows(db, project, manifest)
    _seed_pack_workbenches(db, project, manifest)
    return roles


def _seed_record_types_from_manifest(
    db: Session, project: Project, manifest: PackManifest
) -> None:
    for et in manifest.entity_types:
        existing = db.scalar(
            select(ProjectRecordType.id).where(
                ProjectRecordType.project_id == project.id,
                ProjectRecordType.key == et.key,
            )
        )
        if existing:
            continue
        parent_json = json.dumps([et.parent_type] if et.parent_type else [], ensure_ascii=False)
        db.add(
            ProjectRecordType(
                project_id=project.id,
                key=et.key,
                label=et.label,
                storage=et.storage,
                field_schema=json.dumps(
                    [f.model_dump() for f in et.fields], ensure_ascii=False
                ),
                parent_types=parent_json,
                orden=et.orden,
            )
        )
    db.flush()


def _seed_pack_roles(
    db: Session, project: Project, manifest: PackManifest
) -> dict[str, ProjectRole]:
    created: dict[str, ProjectRole] = {}
    for role_def in manifest.roles:
        role = ProjectRole(
            project_id=project.id,
            slug=role_def.slug,
            nombre=role_def.nombre,
            is_system=role_def.is_system,
            orden=role_def.orden,
        )
        db.add(role)
        db.flush()
        for cap in role_def.capabilities:
            db.add(ProjectRoleCapability(role_id=role.id, capability_key=cap))
        created[role_def.slug] = role
    return created


def _seed_pack_workflows(db: Session, project: Project, manifest: PackManifest) -> None:
    for entity_type, definition in manifest.workflows.items():
        existing = db.scalar(
            select(ProjectWorkflowDefinition.id).where(
                ProjectWorkflowDefinition.project_id == project.id,
                ProjectWorkflowDefinition.entity_type == entity_type,
                ProjectWorkflowDefinition.is_active.is_(True),
            )
        )
        if existing:
            continue
        db.add(
            ProjectWorkflowDefinition(
                project_id=project.id,
                entity_type=entity_type,
                version=1,
                is_active=True,
                definition=json.dumps(definition, ensure_ascii=False),
            )
        )
    db.flush()


def import_project_pack_config(
    db: Session,
    project: Project,
    payload: dict,
) -> None:
    """Importa JSON exportado (workflows, workbenches, record_types, pack_slug)."""
    from app.services.project_roles import (
        update_workbench_definition,
        update_workflow_definition,
    )

    if slug := payload.get("pack_slug"):
        if isinstance(slug, str) and slug:
            project.pack_slug = slug

    for rt in payload.get("record_types") or []:
        if not isinstance(rt, dict) or not rt.get("key"):
            continue
        key = str(rt["key"])
        existing = db.scalar(
            select(ProjectRecordType).where(
                ProjectRecordType.project_id == project.id,
                ProjectRecordType.key == key,
            )
        )
        field_schema = rt.get("field_schema") or []
        parent_types = rt.get("parent_types") or []
        if existing:
            existing.label = str(rt.get("label") or existing.label)
            existing.storage = str(rt.get("storage") or existing.storage)
            existing.field_schema = json.dumps(field_schema, ensure_ascii=False)
            existing.parent_types = json.dumps(parent_types, ensure_ascii=False)
        else:
            db.add(
                ProjectRecordType(
                    project_id=project.id,
                    key=key,
                    label=str(rt.get("label") or key),
                    storage=str(rt.get("storage") or "generic"),
                    field_schema=json.dumps(field_schema, ensure_ascii=False),
                    parent_types=json.dumps(parent_types, ensure_ascii=False),
                    orden=int(rt.get("orden") or 0),
                )
            )

    workflows = payload.get("workflows") or {}
    if isinstance(workflows, dict):
        for entity_type, definition in workflows.items():
            if isinstance(definition, dict) and definition.get("states"):
                update_workflow_definition(db, project, str(entity_type), definition)

    workbenches = payload.get("workbenches")
    if isinstance(workbenches, list) and workbenches:
        update_workbench_definition(db, project, workbenches)

    db.flush()


def _seed_pack_workbenches(db: Session, project: Project, manifest: PackManifest) -> None:
    if not manifest.workbenches:
        return
    payload = [
        {
            "key": wb.key,
            "label": wb.label,
            "route": wb.route,
            "icon": wb.icon,
            "section": wb.section,
            "view_type": wb.view_type,
            "entity_type": wb.entity_type,
            "required_capabilities": wb.required_capabilities,
            "queue_filter": wb.queue_filter,
            "orden": wb.orden,
        }
        for wb in manifest.workbenches
    ]
    row = db.scalar(
        select(ProjectWorkbenchDefinition).where(
            ProjectWorkbenchDefinition.project_id == project.id
        )
    )
    encoded = json.dumps(payload, ensure_ascii=False)
    if row:
        row.definition = encoded
    else:
        db.add(ProjectWorkbenchDefinition(project_id=project.id, definition=encoded))
    db.flush()
