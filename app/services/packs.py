"""Seed y aplicación de project packs."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.packs.catalog import SYSTEM_PACKS, get_pack_manifest
from app.domain.packs.manifest import BlockDef, PackManifest
from app.models.entities import (
    Project,
    ProjectFieldDefinition,
    ProjectPack,
    ProjectRecordType,
    ProjectRole,
    ProjectRoleCapability,
    ProjectWorkbenchDefinition,
    ProjectWorkflowDefinition,
)
from app.services.blocks import seed_project_blocks, seed_project_views, views_to_workbenches
from app.services.project_roles import seed_project_from_template


def _blocks_from_manifest(manifest: PackManifest) -> list[BlockDef]:
    """Deriva project_blocks desde workbenches cuando el manifest no los declara."""
    if manifest.blocks:
        return manifest.blocks
    blocks: list[BlockDef] = []
    for wb in manifest.workbenches or []:
        if wb.view_type == "custom" or wb.custom_view_key:
            blocks.append(
                BlockDef(
                    key=wb.key,
                    block_slug="custom",
                    label=wb.label,
                    config={
                        "view_type": "custom",
                        "custom_view_key": wb.custom_view_key,
                        "entity_type_key": wb.entity_type,
                        "queue_filter": wb.queue_filter,
                    },
                    orden=wb.orden,
                )
            )
            continue
        if not wb.entity_type:
            if wb.view_type and wb.view_type != "custom" and not wb.custom_view_key:
                blocks.append(
                    BlockDef(
                        key=wb.key,
                        block_slug=wb.view_type,
                        label=wb.label,
                        config={"view_type": wb.view_type},
                        orden=wb.orden,
                    )
                )
            continue
        blocks.append(
            BlockDef(
                key=wb.key,
                block_slug=wb.view_type,
                label=wb.label,
                config={
                    "view_type": wb.view_type,
                    "entity_type_key": wb.entity_type,
                    "queue_filter": wb.queue_filter,
                },
                orden=wb.orden,
            )
        )
    return blocks


def _manifest_to_db(manifest: PackManifest) -> dict:
    return manifest.model_dump()


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
    return PackManifest.model_validate(row.manifest)


def list_record_types(db: Session, project_id: uuid.UUID) -> list[ProjectRecordType]:
    return list(
        db.scalars(
            select(ProjectRecordType)
            .where(ProjectRecordType.project_id == project_id)
            .order_by(ProjectRecordType.orden.asc())
        )
    )


def list_field_definitions(
    db: Session, project_id: uuid.UUID
) -> list[ProjectFieldDefinition]:
    return list(
        db.scalars(
            select(ProjectFieldDefinition)
            .where(ProjectFieldDefinition.project_id == project_id)
            .order_by(
                ProjectFieldDefinition.entity_type_key.asc(),
                ProjectFieldDefinition.orden.asc(),
            )
        )
    )


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
        parent_keys = et.parent_type_keys or ([et.parent_type] if et.parent_type else [])
        field_schema = [f.model_dump() for f in et.fields]
        if existing:
            row = db.get(ProjectRecordType, existing)
            if row:
                row.label = et.label
                row.field_schema = field_schema
                row.parent_types = parent_keys or None
                row.icon = et.icon
                row.traits = et.traits
                row.is_system = et.is_system
                row.orden = et.orden
            continue
        db.add(
            ProjectRecordType(
                project_id=project.id,
                key=et.key,
                label=et.label,
                field_schema=field_schema,
                parent_types=parent_keys or None,
                icon=et.icon,
                traits=et.traits,
                is_system=et.is_system,
                orden=et.orden,
            )
        )
    db.flush()


def _seed_field_definitions_from_manifest(
    db: Session, project: Project, manifest: PackManifest
) -> None:
    project_template = project.template_slug or "default"
    for fd in manifest.field_definitions:
        if fd.template_slugs and project_template not in fd.template_slugs:
            continue
        existing = db.scalar(
            select(ProjectFieldDefinition.id).where(
                ProjectFieldDefinition.project_id == project.id,
                ProjectFieldDefinition.entity_type_key == fd.entity_type_key,
                ProjectFieldDefinition.field_key == fd.field_key,
            )
        )
        if existing:
            continue
        db.add(
            ProjectFieldDefinition(
                project_id=project.id,
                entity_type_key=fd.entity_type_key,
                field_key=fd.field_key,
                label=fd.label,
                field_type=fd.field_type,
                config=fd.config,
                orden=fd.orden,
                is_system=fd.is_system,
            )
        )
    db.flush()


def _seed_pack_roles(
    db: Session,
    project: Project,
    manifest: PackManifest,
    *,
    template_slug: str | None = None,
) -> dict[str, ProjectRole]:
    created: dict[str, ProjectRole] = {}
    for role_def in manifest.roles:
        if template_slug and role_def.template_slugs:
            if template_slug not in role_def.template_slugs:
                continue
        existing = db.scalar(
            select(ProjectRole).where(
                ProjectRole.project_id == project.id,
                ProjectRole.slug == role_def.slug,
            )
        )
        if existing:
            created[role_def.slug] = existing
            continue
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


def _resolve_workflows(
    manifest: PackManifest, template_slug: str
) -> dict[str, dict]:
    if manifest.workflow_profiles:
        return manifest.workflow_profiles.get(
            template_slug,
            manifest.workflow_profiles.get("default", {}),
        )
    if manifest.workflow_variants:
        return manifest.workflow_variants.get(template_slug, {})
    return manifest.workflows


def _seed_pack_workflows(
    db: Session, project: Project, manifest: PackManifest
) -> None:
    template_slug = project.template_slug or "default"
    workflows = _resolve_workflows(manifest, template_slug)
    for entity_type, definition in workflows.items():
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
                definition=definition,
            )
        )
    db.flush()


def _seed_workbenches_from_manifest(
    db: Session, project: Project, manifest: PackManifest
) -> None:
    if not manifest.workbenches:
        return
    payload = [
        {
            "key": wb.key,
            "label": wb.label,
            "route": wb.route,
            "icon": wb.icon,
            "section": wb.section,
            "required_capabilities": wb.required_capabilities,
            "orden": wb.orden,
            "view_type": wb.view_type,
            "entity_type": wb.entity_type,
            "custom_view_key": wb.custom_view_key,
            "queue_filter": wb.queue_filter,
        }
        for wb in manifest.workbenches
    ]
    row = db.scalar(
        select(ProjectWorkbenchDefinition).where(
            ProjectWorkbenchDefinition.project_id == project.id
        )
    )
    if row:
        row.definition = payload
    else:
        db.add(ProjectWorkbenchDefinition(project_id=project.id, definition=payload))
    db.flush()


def _seed_pack_workbenches_from_views(db: Session, project: Project) -> None:
    from app.services.blocks import list_project_blocks, list_project_views

    views = list_project_views(db, project.id)
    if not views:
        return
    blocks_by_key = {b.key: b for b in list_project_blocks(db, project.id)}
    payload = []
    for v in views:
        wb: dict = {
            "key": v.key,
            "label": v.label,
            "route": v.route,
            "icon": v.icon,
            "section": v.section,
            "required_capabilities": v.required_capabilities or [],
            "orden": v.orden,
        }
        layout = v.layout or {}
        block_refs = layout.get("blocks") or []
        nav = layout.get("nav") or {}
        if nav.get("group"):
            wb["nav_group"] = nav["group"]
            wb["nav_group_label"] = nav.get("group_label")
            wb["nav_group_order"] = nav.get("group_order", 0)
            wb["nav_primary"] = nav.get("primary", True)
        if block_refs:
            bk = block_refs[0].get("project_block_key")
            block = blocks_by_key.get(bk) if bk else None
            if block:
                cfg = block.config or {}
                wb["view_type"] = cfg.get("view_type", block.block_slug)
                wb["entity_type"] = cfg.get("entity_type_key")
                wb["queue_filter"] = cfg.get("queue_filter")
                if cfg.get("custom_view_key"):
                    wb["custom_view_key"] = cfg.get("custom_view_key")
        payload.append(wb)
    row = db.scalar(
        select(ProjectWorkbenchDefinition).where(
            ProjectWorkbenchDefinition.project_id == project.id
        )
    )
    if row:
        row.definition = payload
    else:
        db.add(ProjectWorkbenchDefinition(project_id=project.id, definition=payload))
    db.flush()


def _seed_communication_rules_from_manifest(
    db: Session,
    project: Project,
    manifest: PackManifest,
) -> None:
    from app.schemas.communication_rules import CommunicationRule
    from app.services.communication.legacy_defaults import default_communication_rules_for_pack
    from app.services.communication.store import update_communication_rules

    if manifest.communication_rules:
        rules = [CommunicationRule.model_validate(r) for r in manifest.communication_rules]
    else:
        rules = default_communication_rules_for_pack(manifest.slug)
    update_communication_rules(db, project, rules)


def seed_project_from_manifest(
    db: Session,
    project: Project,
    manifest: PackManifest,
    *,
    template_slug: str | None = None,
    project_structure=None,
    initial_created_by=None,
) -> dict[str, ProjectRole]:
    """Aplica manifest al proyecto: entity types, fields, roles, workflows, blocks, views."""
    from app.schemas.project_structure import ProjectStructureDef
    from app.services.project_structure import (
        merge_pack_with_structure,
        patch_scope_block_config,
        seed_initial_root_records,
        sync_entity_capabilities,
    )

    template_slug = project.template_slug or "default"
    if project_structure is not None:
        if isinstance(project_structure, dict):
            project_structure = ProjectStructureDef.model_validate(project_structure)
        manifest = merge_pack_with_structure(
            manifest, project_structure, template_slug=template_slug
        )

    _seed_record_types_from_manifest(db, project, manifest)
    _seed_field_definitions_from_manifest(db, project, manifest)

    def _passes_filter(item: BlockDef, ts: str) -> bool:
        if item.template_slugs and ts not in item.template_slugs:
            return False
        if item.exclude_template_slugs and ts in item.exclude_template_slugs:
            return False
        return True

    block_defs = _blocks_from_manifest(manifest)
    if block_defs:
        filtered_blocks = [b for b in block_defs if _passes_filter(b, template_slug)]
        seed_project_blocks(db, project, filtered_blocks)
    if manifest.project_views:
        from app.domain.packs.manifest import ViewDef as _VD
        filtered_views = [v for v in manifest.project_views if _passes_filter(v, template_slug)]  # type: ignore[arg-type]
        seed_project_views(db, project, filtered_views)
    elif manifest.workbenches:
        from app.domain.packs.manifest import ViewDef

        views = [
            ViewDef(
                key=wb.key,
                label=wb.label,
                route=wb.route,
                icon=wb.icon,
                section=wb.section,
                layout={"blocks": [{"project_block_key": wb.key, "width": "full"}]},
                required_capabilities=wb.required_capabilities,
                orden=wb.orden,
                view_type=wb.view_type,
                entity_type=wb.entity_type,
                queue_filter=wb.queue_filter,
            )
            for wb in manifest.workbenches
        ]
        seed_project_views(db, project, views)
        _seed_workbenches_from_manifest(db, project, manifest)

    roles = _seed_pack_roles(
        db, project, manifest, template_slug=template_slug or project.template_slug
    )
    _seed_pack_workflows(db, project, manifest)
    _seed_communication_rules_from_manifest(db, project, manifest)

    if project_structure is not None:
        entity_keys = [et.key for et in manifest.entity_types]
        workflows = manifest.workflows or {}
        if manifest.workflow_profiles:
            workflows = manifest.workflow_profiles.get(template_slug, workflows)
        sync_entity_capabilities(
            db, project, entity_keys, roles, workflows=workflows
        )
        patch_scope_block_config(db, project, manifest)
        if initial_created_by is not None:
            seed_initial_root_records(
                db,
                project,
                project_structure,
                created_by=initial_created_by,
            )

    _seed_pack_workbenches_from_views(db, project)
    from app.services.scrum_v2_structure import apply_scrum_v2_structure

    apply_scrum_v2_structure(db, project)
    return roles


def seed_project_from_pack(
    db: Session,
    project: Project,
    pack_slug: str,
    *,
    template_slug: str | None = None,
    project_structure=None,
    initial_created_by=None,
) -> dict[str, ProjectRole]:
    """Aplica pack al proyecto: entity types, fields, roles, workflows, blocks, views."""
    manifest = get_pack_manifest(pack_slug)
    if manifest is None:
        raise ValueError(f"Pack desconocido: {pack_slug}")

    project.pack_slug = pack_slug
    if template_slug:
        project.template_slug = template_slug
    elif manifest.maps_template_slug and not project.template_slug:
        project.template_slug = manifest.maps_template_slug

    return seed_project_from_manifest(
        db,
        project,
        manifest,
        template_slug=template_slug,
        project_structure=project_structure,
        initial_created_by=initial_created_by,
    )


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
            existing.field_schema = field_schema
            existing.parent_types = parent_types or None
        else:
            db.add(
                ProjectRecordType(
                    project_id=project.id,
                    key=key,
                    label=str(rt.get("label") or key),
                    field_schema=field_schema,
                    parent_types=parent_types or None,
                    orden=int(rt.get("orden") or 0),
                )
            )

    workflows = payload.get("workflows") or {}
    if isinstance(workflows, dict):
        for entity_type, definition in workflows.items():
            if isinstance(definition, dict) and definition.get("states"):
                update_workflow_definition(db, project, str(entity_type), definition)[0]

    workbenches = payload.get("workbenches")
    if isinstance(workbenches, list) and workbenches:
        update_workbench_definition(db, project, workbenches)

    comm_rules = payload.get("communication_rules")
    if isinstance(comm_rules, list) and comm_rules:
        from app.schemas.communication_rules import CommunicationRule
        from app.services.communication.store import update_communication_rules

        update_communication_rules(
            db,
            project,
            [CommunicationRule.model_validate(r) for r in comm_rules],
        )

    db.flush()
