"""Merge de estructura custom con pack manifest, vistas derivadas y capabilities."""
from __future__ import annotations

import copy
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.packs.catalog import _simple_tarea_workflow
from app.domain.packs.manifest import BlockDef, EntityTypeDef, FieldDef, PackManifest, PackWorkbenchDef, ViewDef
from app.models.entities import (
    Project,
    ProjectBlock,
    ProjectRecord,
    ProjectRecordType,
    ProjectRole,
    ProjectRoleCapability,
)
from app.schemas.project_structure import (
    ProjectStructureDef,
    ProjectStructureEntity,
    ProjectStructureField,
)
from app.services.role_capabilities import ensure_role_capabilities_for_role, primary_admin_role


def validate_structure_entities(entities: list[ProjectStructureEntity]) -> None:
    if not entities:
        raise ValueError("Se requiere al menos un tipo de entidad")
    keys = [e.key for e in entities]
    if len(keys) != len(set(keys)):
        raise ValueError("Keys de entity types duplicadas")
    key_set = set(keys)
    roots = [e for e in entities if not e.parent_type_keys]
    for entity in entities:
        for parent in entity.parent_type_keys:
            if parent not in key_set:
                raise ValueError(f"Padre '{parent}' no existe para tipo '{entity.key}'")
            if parent == entity.key:
                raise ValueError(f"Un tipo no puede ser padre de sí mismo: '{entity.key}'")
    if _has_cycle(entities):
        raise ValueError("La jerarquía contiene un ciclo")
    if not roots:
        raise ValueError("Se requiere al menos un tipo raíz (sin padre)")


def _has_cycle(entities: list[ProjectStructureEntity]) -> bool:
    children_of: dict[str, list[str]] = {e.key: [] for e in entities}
    for entity in entities:
        for parent in entity.parent_type_keys:
            children_of.setdefault(parent, []).append(entity.key)

    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for child in children_of.get(node, []):
            if dfs(child):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    for key in children_of:
        if dfs(key):
            return True
    return False


def _structure_entity_to_def(entity: ProjectStructureEntity) -> EntityTypeDef:
    hierarchy = "root" if not entity.parent_type_keys else "child"
    parent_type = entity.parent_type_keys[0] if len(entity.parent_type_keys) == 1 else None
    return EntityTypeDef(
        key=entity.key,
        label=entity.label,
        hierarchy=hierarchy,  # type: ignore[arg-type]
        parent_type=parent_type,
        parent_type_keys=list(entity.parent_type_keys),
        fields=[
            FieldDef(
                id=f.id,
                label=f.label,
                type=f.type,  # type: ignore[arg-type]
                required=f.required,
                options=f.options,
            )
            for f in entity.fields
        ],
        traits=entity.traits,
        icon=entity.icon,
        is_system=False,
        orden=entity.orden,
    )


def _default_workflow_for_entity(
    entity_key: str,
    base: PackManifest,
    template_slug: str,
    user_workflow: dict[str, Any] | None,
) -> dict[str, Any]:
    if user_workflow and user_workflow.get("states"):
        return copy.deepcopy(user_workflow)
    resolved = base.workflows or {}
    if base.workflow_profiles:
        resolved = base.workflow_profiles.get(
            template_slug,
            base.workflow_profiles.get("default", {}),
        )
    if entity_key in resolved:
        return copy.deepcopy(resolved[entity_key])
    wf = copy.deepcopy(_simple_tarea_workflow())
    for transition in wf.get("transitions", []):
        transition["required_capabilities"] = [
            cap.replace("record.tarea.", f"record.{entity_key}.")
            for cap in transition.get("required_capabilities", [])
        ]
    return wf


def merge_pack_with_structure(
    base: PackManifest,
    structure: ProjectStructureDef,
    *,
    template_slug: str = "default",
) -> PackManifest:
    validate_structure_entities(structure.entity_types)
    merged = base.model_copy(deep=True)
    entity_defs = [_structure_entity_to_def(e) for e in structure.entity_types]
    merged.entity_types = entity_defs

    structure_keys = {e.key for e in structure.entity_types}
    merged.field_definitions = [
        fd for fd in merged.field_definitions if fd.entity_type_key in structure_keys
    ]

    workflows: dict[str, dict[str, Any]] = {}
    for entity in structure.entity_types:
        workflows[entity.key] = _default_workflow_for_entity(
            entity.key, base, template_slug, entity.workflow
        )
    merged.workflows = workflows
    if merged.workflow_profiles:
        merged.workflow_profiles = {
            tmpl: {k: v for k, v in prof.items() if k in structure_keys}
            for tmpl, prof in merged.workflow_profiles.items()
        }
        merged.workflow_profiles.setdefault(template_slug, workflows)

    merged = _apply_derived_views(merged, entity_defs)
    return merged


def _scope_levels(entity_defs: list[EntityTypeDef]) -> list[str]:
    roots = [et for et in entity_defs if not (et.parent_type_keys or et.parent_type)]
    if not roots:
        return []
    root = sorted(roots, key=lambda e: e.orden)[0]
    levels = [root.key]
    current = root.key
    while True:
        children = [
            et
            for et in entity_defs
            if current in (et.parent_type_keys or ([et.parent_type] if et.parent_type else []))
        ]
        children.sort(key=lambda e: e.orden)
        chain = [c for c in children if (c.traits or {}).get("scope_chain")]
        pool = chain if chain else children[:1]
        if not pool:
            break
        nxt = pool[0]
        if nxt.key in levels:
            break
        levels.append(nxt.key)
        current = nxt.key
    return levels


def _scope_hierarchy(entity_defs: list[EntityTypeDef]) -> tuple[str | None, list[str]]:
    roots = [et for et in entity_defs if not (et.parent_type_keys or et.parent_type)]
    if not roots:
        return None, []
    root = sorted(roots, key=lambda e: e.orden)[0]
    children = [
        et.key
        for et in entity_defs
        if root.key in (et.parent_type_keys or ([et.parent_type] if et.parent_type else []))
    ]
    return root.key, children


def _apply_derived_views(manifest: PackManifest, entity_defs: list[EntityTypeDef]) -> PackManifest:
    root_key, child_keys = _scope_hierarchy(entity_defs)
    if not root_key:
        return manifest

    scope_config = {
        "view_type": "scope",
        "root_entity_type": root_key,
        "child_entity_types": child_keys,
        "scope_entity_types": [et.key for et in sorted(entity_defs, key=lambda e: e.orden)],
        "scope_config": {
            "levels": _scope_levels(entity_defs),
            "depth_actions": "any_level",
            "show_summary": True,
            "allow_reparent": True,
        },
    }

    kanban_types = [et.key for et in entity_defs if (et.traits or {}).get("kanban")]

    if manifest.project_views:
        updated_views: list[ViewDef] = []
        scope_found = False
        for view in manifest.project_views:
            if view.key == "scope":
                scope_found = True
                layout = dict(view.layout or {})
                blocks = layout.get("blocks") or [{"project_block_key": "scope", "width": "full"}]
                updated_views.append(view.model_copy(update={"layout": layout}))
            else:
                updated_views.append(view)
        if not scope_found:
            updated_views.append(
                ViewDef(
                    key="scope",
                    label="Alcance",
                    route="scope",
                    icon="flag",
                    section="plan",
                    layout={"blocks": [{"project_block_key": "scope", "width": "full"}]},
                    required_capabilities=[f"record.{root_key}.read"],
                    orden=35,
                    view_type="custom",
                )
            )
        manifest.project_views = updated_views

        if manifest.blocks:
            new_blocks: list[BlockDef] = []
            scope_block_found = False
            for block in manifest.blocks:
                if block.key == "scope":
                    scope_block_found = True
                    cfg = dict(block.config or {})
                    cfg.update(scope_config)
                    new_blocks.append(block.model_copy(update={"config": cfg}))
                elif block.config and block.config.get("entity_type_key") in {
                    et.key for et in entity_defs
                }:
                    new_blocks.append(block)
                elif block.key in {"kanban", "my_tasks"} and kanban_types:
                    cfg = dict(block.config or {})
                    cfg["entity_type_key"] = kanban_types[0]
                    board_cfg = dict(cfg.get("board_config") or {})
                    board_cfg.setdefault(
                        "filters",
                        {"search": True, "parent_chain": True},
                    )
                    board_cfg.setdefault("column_picker", True)
                    cfg["board_config"] = board_cfg
                    new_blocks.append(block.model_copy(update={"config": cfg}))
                else:
                    new_blocks.append(block)
            if not scope_block_found:
                new_blocks.append(
                    BlockDef(
                        block_slug="scope",
                        key="scope",
                        label="Alcance",
                        config=scope_config,
                        orden=35,
                    )
                )
            manifest.blocks = new_blocks
    else:
        workbenches = list(manifest.workbenches or [])
        if not any(wb.key == "scope" for wb in workbenches):
            workbenches.append(
                PackWorkbenchDef(
                    key="scope",
                    label="Alcance",
                    route="scope",
                    icon="flag",
                    section="plan",
                    view_type="custom",
                    required_capabilities=[f"record.{root_key}.read"],
                    orden=5,
                )
            )
        manifest.workbenches = workbenches

    return manifest


def entity_capability_keys(entity_key: str, workflow: dict[str, Any] | None = None) -> list[str]:
    caps = [
        f"record.{entity_key}.read",
        f"record.{entity_key}.create",
        f"record.{entity_key}.edit",
    ]
    if workflow:
        for transition in workflow.get("transitions") or []:
            for cap in transition.get("required_capabilities") or []:
                if isinstance(cap, str) and cap.startswith(f"record.{entity_key}."):
                    caps.append(cap)
    else:
        caps.extend(
            [
                f"record.{entity_key}.transition.iniciar",
                f"record.{entity_key}.transition.completar",
                f"record.{entity_key}.transition.cancelar",
            ]
        )
    return list(dict.fromkeys(caps))


def sync_entity_capabilities(
    db: Session,
    project: Project,
    entity_keys: list[str],
    roles: dict[str, ProjectRole],
    *,
    workflows: dict[str, dict[str, Any]] | None = None,
) -> None:
    from app.services.project_roles import list_project_roles

    all_roles = list(roles.values()) or list_project_roles(db, project.id)
    admin = primary_admin_role(all_roles)
    root_key = None
    child_key = None
    for rt in list(
        db.scalars(
            select(ProjectRecordType)
            .where(ProjectRecordType.project_id == project.id)
            .order_by(ProjectRecordType.orden.asc())
        )
    ):
        parents = rt.parent_types or []
        if not parents and root_key is None:
            root_key = rt.key
        elif root_key and rt.key != root_key and child_key is None:
            if root_key in parents:
                child_key = rt.key

    all_caps: list[str] = []
    for key in entity_keys:
        wf = (workflows or {}).get(key)
        all_caps.extend(entity_capability_keys(key, wf))

    for role in all_roles:
        has_record_cap = db.scalar(
            select(ProjectRoleCapability.capability_key)
            .where(
                ProjectRoleCapability.role_id == role.id,
                ProjectRoleCapability.capability_key.like("record.%"),
            )
            .limit(1)
        )
        if role == admin or has_record_cap or role.slug in {"pm", "pm_tecnico", "owner", "coordinador"}:
            ensure_role_capabilities_for_role(db, role, all_caps)


def patch_scope_block_config(db: Session, project: Project, manifest: PackManifest) -> None:
    root_key, child_keys = _scope_hierarchy(manifest.entity_types)
    if not root_key:
        return
    scope_config = {
        "view_type": "scope",
        "root_entity_type": root_key,
        "child_entity_types": child_keys,
        "scope_entity_types": [et.key for et in manifest.entity_types],
    }
    block = db.scalar(
        select(ProjectBlock).where(
            ProjectBlock.project_id == project.id,
            ProjectBlock.key == "scope",
        )
    )
    if block:
        cfg = dict(block.config or {})
        cfg.update(scope_config)
        block.config = cfg
        db.flush()


def seed_initial_root_records(
    db: Session,
    project: Project,
    structure: ProjectStructureDef,
    *,
    created_by: uuid.UUID,
) -> None:
    if not structure.initial_roots:
        return
    root_key, _ = _scope_hierarchy(
        [_structure_entity_to_def(e) for e in structure.entity_types]
    )
    from app.services.records import generic_store

    for idx, item in enumerate(structure.initial_roots):
        record_type = item.record_type or root_key
        if not record_type:
            continue
        created = generic_store.create_record(
            db,
            project,
            record_type=record_type,
            titulo=item.titulo,
            descripcion=item.descripcion,
            created_by=created_by,
        )
        orden = item.orden if item.orden else idx
        if orden:
            row = db.get(ProjectRecord, created.id)
            if row is not None:
                row.orden = orden
                db.flush()


def structure_from_record_types(
    rows: list[ProjectRecordType],
) -> list[ProjectStructureEntity]:
    entities: list[ProjectStructureEntity] = []
    for rt in rows:
        parents = rt.parent_types or []
        fields_raw = rt.field_schema or []
        entities.append(
            ProjectStructureEntity(
                key=rt.key,
                label=rt.label,
                parent_type_keys=parents,
                icon=rt.icon,
                traits=rt.traits or {},
                fields=[
                    ProjectStructureField(
                        id=f.get("id", f.get("field_key", "")),
                        label=f.get("label", ""),
                        type=f.get("type", f.get("field_type", "text")),
                    )
                    for f in fields_raw
                    if isinstance(f, dict) and (f.get("id") or f.get("field_key"))
                ],
                orden=rt.orden,
            )
        )
    return entities


def add_entity_type_to_project(
    db: Session,
    project: Project,
    entity: ProjectStructureEntity,
    roles: dict[str, ProjectRole] | None = None,
) -> ProjectRecordType:
    from app.domain.packs.manifest import PackManifest
    from app.services.packs import (
        _seed_pack_workflows,
        _seed_record_types_from_manifest,
        get_project_pack_manifest,
        list_record_types,
    )
    from app.services.project_roles import list_project_roles, update_workflow_definition

    existing_rows = list_record_types(db, project.id)
    entities = structure_from_record_types(existing_rows)
    entities.append(entity)
    validate_structure_entities(entities)

    manifest = get_project_pack_manifest(db, project) or PackManifest(
        slug=project.pack_slug or "custom", nombre=""
    )
    template_slug = project.template_slug or "default"
    wf = _default_workflow_for_entity(entity.key, manifest, template_slug, entity.workflow)

    _seed_record_types_from_manifest(
        db,
        project,
        PackManifest(slug=manifest.slug, nombre="", entity_types=[_structure_entity_to_def(entity)]),
    )
    update_workflow_definition(db, project, entity.key, wf)
    if roles is None:
        roles = {r.slug: r for r in list_project_roles(db, project.id)}
    sync_entity_capabilities(
        db,
        project,
        [e.key for e in entities],
        roles,
        workflows={entity.key: wf},
    )

    all_entities = [_structure_entity_to_def(e) for e in entities]
    patch_scope_block_config(
        db,
        project,
        manifest.model_copy(update={"entity_types": all_entities}),
    )
    from app.services.packs import _seed_pack_workbenches_from_views

    _seed_pack_workbenches_from_views(db, project)

    row = db.scalar(
        select(ProjectRecordType).where(
            ProjectRecordType.project_id == project.id,
            ProjectRecordType.key == entity.key,
        )
    )
    if row is None:
        raise HTTPException(status_code=500, detail="No se pudo crear entity type")
    return row


def update_entity_type_on_project(
    db: Session,
    project: Project,
    key: str,
    *,
    label: str | None = None,
    icon: str | None = None,
    traits: dict | None = None,
    parent_type_keys: list[str] | None = None,
    field_schema: list[dict] | None = None,
    orden: int | None = None,
) -> ProjectRecordType:
    from app.services.packs import list_record_types

    rt = db.scalar(
        select(ProjectRecordType).where(
            ProjectRecordType.project_id == project.id,
            ProjectRecordType.key == key,
        )
    )
    if rt is None:
        raise HTTPException(status_code=404, detail="Entity type no encontrado")

    if parent_type_keys is not None:
        entities = structure_from_record_types(list_record_types(db, project.id))
        updated = []
        for entity in entities:
            if entity.key == key:
                updated.append(
                    entity.model_copy(update={"parent_type_keys": parent_type_keys})
                )
            else:
                updated.append(entity)
        validate_structure_entities(updated)
        rt.parent_types = parent_type_keys or None

    if label is not None:
        rt.label = label
    if icon is not None:
        rt.icon = icon
    if traits is not None:
        rt.traits = traits
    if field_schema is not None:
        rt.field_schema = field_schema
    if orden is not None:
        rt.orden = orden
    db.flush()
    return rt


def assert_entity_type_deletable(db: Session, project_id: uuid.UUID, key: str) -> None:
    count = db.scalar(
        select(func.count())
        .select_from(ProjectRecord)
        .where(
            ProjectRecord.project_id == project_id,
            ProjectRecord.record_type == key,
        )
    )
    if count and count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede eliminar '{key}': tiene registros asociados",
        )


def delete_entity_type_from_project(db: Session, project: Project, key: str) -> None:
    assert_entity_type_deletable(db, project.id, key)
    rt = db.scalar(
        select(ProjectRecordType).where(
            ProjectRecordType.project_id == project.id,
            ProjectRecordType.key == key,
        )
    )
    if rt is None:
        raise HTTPException(status_code=404, detail="Entity type no encontrado")
    db.delete(rt)
    db.flush()
