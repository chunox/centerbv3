"""API de contexto de acceso, roles y workflows por proyecto."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth_deps import AuthContext, get_optional_auth
from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.domain.capabilities import CAPABILITY_CATALOG, CapabilityDef
from app.domain.workbenches import DEFAULT_WORKBENCHES, SECTION_LABELS
from app.domain.workflow_templates import workflow_for_project_tipo
from app.models.entities import ProjectMember, ProjectRole, ProjectWorkflowDefinition
from app.schemas.access_context import (
    CapabilityDefRead,
    PackContextRead,
    ProjectAccessContextRead,
    ProjectRoleCapabilitiesUpdate,
    ProjectRoleCreate,
    ProjectRoleRead,
    ProjectWorkbenchesUpdate,
    ProjectWorkflowUpdate,
    RecordTypeRead,
    WorkflowTemplateApply,
    WorkbenchRead,
    WorkflowSummaryRead,
)
from app.schemas.projects import ProjectMemberCreate, ProjectMemberRead
from app.services.project_members import add_project_member, remove_project_member
from app.services.project_roles import (
    assign_member_role,
    create_custom_role,
    delete_custom_role,
    get_role_capabilities,
    list_project_roles,
    remove_member_role,
    update_role_capabilities,
    update_workbench_definition,
    update_workflow_definition,
)
from app.services.workflow.authorize import assert_capability
from app.services.workflow.capabilities import get_effective_capabilities, get_user_role_assignments
from app.services.packs import get_project_pack_manifest, import_project_pack_config, list_record_types
from app.services.records.registry import registry
from app.services.workflow.store import (
    WORKFLOW_ENTITY_TYPES,
    get_active_workflow,
    get_active_workflow_version,
    get_all_active_workflows,
    get_workbenches,
    workflow_entity_types,
)
from app.domain.capabilities import PROJECT_MEMBERS_MANAGE, PROJECT_ROLES_MANAGE

router = APIRouter(prefix="/projects", tags=["project-access"])


def _resolve_user_id(auth: AuthContext | None, user_id: UUID | None) -> UUID:
    if user_id is not None:
        return user_id
    if auth is not None:
        return auth.user.id
    raise HTTPException(status_code=401, detail="Se requiere autenticación")


def _role_to_read(db: Session, role: ProjectRole) -> ProjectRoleRead:
    return ProjectRoleRead(
        id=role.id,
        project_id=role.project_id,
        slug=role.slug,
        nombre=role.nombre,
        descripcion=role.descripcion,
        color=role.color,
        is_system=role.is_system,
        orden=role.orden,
        capabilities=get_role_capabilities(db, role.id),
    )


@router.get("/{project_id}/access-context", response_model=ProjectAccessContextRead)
def get_access_context(
    project_id: UUID,
    user_id: UUID | None = None,
    auth: AuthContext | None = Depends(get_optional_auth),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    effective_user = _resolve_user_id(auth, user_id)

    assignments = get_user_role_assignments(db, project.id, effective_user)
    caps = sorted(get_effective_capabilities(db, project.id, effective_user))

    workflows: dict[str, WorkflowSummaryRead] = {}
    for entity_type in workflow_entity_types(db, project.id):
        defn = get_active_workflow(db, project.id, entity_type)
        if defn is None:
            continue
        version = get_active_workflow_version(db, project.id, entity_type) or 1
        workflows[entity_type] = WorkflowSummaryRead(
            entity_type=entity_type,
            version=version,
            states=defn.get("states", []),
            transitions=defn.get("transitions", []),
            initial_state=defn.get("initial_state"),
            terminal_states=defn.get("terminal_states", []),
        )

    wb_raw = get_workbenches(db, project.id)
    visible_workbenches: list[WorkbenchRead] = []
    cap_set = set(caps)
    for wb in sorted(wb_raw, key=lambda w: w.get("orden", 0)):
        required = wb.get("required_capabilities", [])
        if not required or any(r in cap_set for r in required):
            visible_workbenches.append(
                WorkbenchRead(
                    key=wb["key"],
                    label=wb["label"],
                    route=wb["route"],
                    icon=wb.get("icon", "circle"),
                    section=wb.get("section", "plan"),
                    view_type=wb.get("view_type", "custom"),
                    entity_type=wb.get("entity_type"),
                    required_capabilities=required,
                    queue_filter=wb.get("queue_filter"),
                    orden=wb.get("orden", 0),
                )
            )

    catalog = [
        CapabilityDefRead(key=c.key, label=c.label, group=c.group, description=c.description)
        for c in CAPABILITY_CATALOG
    ]

    pack_manifest = get_project_pack_manifest(db, project)
    pack_ctx = None
    if pack_manifest:
        pack_ctx = PackContextRead(
            slug=pack_manifest.slug,
            nombre=pack_manifest.nombre,
            descripcion=pack_manifest.descripcion,
            views=[v.model_dump() for v in pack_manifest.views],
        )

    record_types: list[RecordTypeRead] = []
    for rt in list_record_types(db, project.id):
        try:
            fields = json.loads(rt.field_schema) if rt.field_schema else []
        except json.JSONDecodeError:
            fields = []
        try:
            parents = json.loads(rt.parent_types) if rt.parent_types else []
        except json.JSONDecodeError:
            parents = []
        record_types.append(
            RecordTypeRead(
                key=rt.key,
                label=rt.label,
                storage=rt.storage,
                field_schema=fields,
                parent_types=parents,
                orden=rt.orden,
            )
        )

    return ProjectAccessContextRead(
        user_id=effective_user,
        roles=[_role_to_read(db, r) for r in assignments],
        capabilities=caps,
        workflows=workflows,
        workbenches=visible_workbenches,
        capability_catalog=catalog,
        pack=pack_ctx,
        record_types=record_types,
        pack_slug=project.pack_slug,
    )


@router.get("/{project_id}/pack/export")
def export_project_pack(
    project_id: UUID,
    actor_user_id: UUID,
    db: Session = Depends(get_db),
):
    """Exporta configuración del proyecto (pack, roles, workflows, workbenches)."""
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, PROJECT_ROLES_MANAGE)
    manifest = get_project_pack_manifest(db, project)
    roles = list_project_roles(db, project.id)
    workflows = get_all_active_workflows(db, project.id)
    workbenches = get_workbenches(db, project.id)
    record_types = list_record_types(db, project.id)
    return {
        "pack_slug": project.pack_slug,
        "manifest": manifest.model_dump() if manifest else None,
        "roles": [
            {
                "slug": r.slug,
                "nombre": r.nombre,
                "capabilities": get_role_capabilities(db, r.id),
            }
            for r in roles
        ],
        "workflows": workflows,
        "workbenches": workbenches,
        "record_types": [
            {
                "key": rt.key,
                "label": rt.label,
                "storage": rt.storage,
                "field_schema": json.loads(rt.field_schema or "[]"),
                "parent_types": json.loads(rt.parent_types or "[]"),
            }
            for rt in record_types
        ],
    }


@router.post("/{project_id}/pack/import", status_code=204)
def import_project_pack(
    project_id: UUID,
    payload: dict,
    actor_user_id: UUID,
    db: Session = Depends(get_db),
):
    """Importa configuración exportada (workflows, workbenches, record_types)."""
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, PROJECT_ROLES_MANAGE)
    import_project_pack_config(db, project, payload)
    db.commit()


@router.get("/{project_id}/roles", response_model=list[ProjectRoleRead])
def list_roles(project_id: UUID, db: Session = Depends(get_db)):
    get_project_or_404(project_id, db)
    roles = list_project_roles(db, project_id)
    return [_role_to_read(db, r) for r in roles]


@router.post("/{project_id}/roles", response_model=ProjectRoleRead, status_code=201)
def create_role(
    project_id: UUID,
    payload: ProjectRoleCreate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, payload.actor_user_id, PROJECT_ROLES_MANAGE)
    role = create_custom_role(
        db,
        project,
        slug=payload.slug,
        nombre=payload.nombre,
        capability_keys=payload.capability_keys,
        descripcion=payload.descripcion,
        color=payload.color,
    )
    db.commit()
    db.refresh(role)
    return _role_to_read(db, role)


@router.patch("/{project_id}/roles/{role_id}/capabilities", response_model=ProjectRoleRead)
def patch_role_capabilities(
    project_id: UUID,
    role_id: UUID,
    payload: ProjectRoleCapabilitiesUpdate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, payload.actor_user_id, PROJECT_ROLES_MANAGE)
    role = db.get(ProjectRole, role_id)
    if not role or role.project_id != project.id:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    update_role_capabilities(db, role, payload.capability_keys)
    db.commit()
    db.refresh(role)
    return _role_to_read(db, role)


@router.delete("/{project_id}/roles/{role_id}", status_code=204)
def delete_role(
    project_id: UUID,
    role_id: UUID,
    actor_user_id: UUID,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, PROJECT_ROLES_MANAGE)
    role = db.get(ProjectRole, role_id)
    if not role or role.project_id != project.id:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    delete_custom_role(db, role)
    db.commit()


@router.put("/{project_id}/workflows/{entity_type}", response_model=WorkflowSummaryRead)
def put_workflow(
    project_id: UUID,
    entity_type: str,
    payload: ProjectWorkflowUpdate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, payload.actor_user_id, PROJECT_ROLES_MANAGE)
    allowed = set(workflow_entity_types(db, project.id))
    if entity_type not in allowed:
        raise HTTPException(status_code=422, detail="entity_type inválido")
    wf = update_workflow_definition(db, project, entity_type, payload.definition)
    db.commit()
    defn = json.loads(wf.definition)
    return WorkflowSummaryRead(
        entity_type=entity_type,
        version=wf.version,
        states=defn.get("states", []),
        transitions=defn.get("transitions", []),
        initial_state=defn.get("initial_state"),
        terminal_states=defn.get("terminal_states", []),
    )


@router.put("/{project_id}/workbenches", response_model=list[WorkbenchRead])
def put_workbenches(
    project_id: UUID,
    payload: ProjectWorkbenchesUpdate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, payload.actor_user_id, PROJECT_ROLES_MANAGE)
    update_workbench_definition(db, project, payload.workbenches)
    db.commit()
    return [
        WorkbenchRead(
            key=wb["key"],
            label=wb["label"],
            route=wb["route"],
            icon=wb.get("icon", "circle"),
            section=wb.get("section", "plan"),
            required_capabilities=wb.get("required_capabilities", []),
            queue_filter=wb.get("queue_filter"),
            orden=wb.get("orden", 0),
        )
        for wb in payload.workbenches
    ]


@router.get("/{project_id}/workbench-sections")
def get_workbench_sections():
    return SECTION_LABELS


@router.get("/{project_id}/workflow-templates/{entity_type}")
def get_workflow_template(
    project_id: UUID,
    entity_type: str,
    user_id: UUID,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, user_id, PROJECT_ROLES_MANAGE)
    allowed = set(workflow_entity_types(db, project.id))
    if entity_type not in allowed:
        raise HTTPException(status_code=422, detail="entity_type inválido")
    return workflow_for_project_tipo(project.tipo, entity_type)


@router.post(
    "/{project_id}/workflow-templates/{entity_type}/apply",
    response_model=WorkflowSummaryRead,
)
def apply_workflow_template(
    project_id: UUID,
    entity_type: str,
    payload: WorkflowTemplateApply,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, payload.actor_user_id, PROJECT_ROLES_MANAGE)
    allowed = set(workflow_entity_types(db, project.id))
    if entity_type not in allowed:
        raise HTTPException(status_code=422, detail="entity_type inválido")
    tipo = payload.project_tipo or project.tipo
    definition = workflow_for_project_tipo(tipo, entity_type)
    wf = update_workflow_definition(db, project, entity_type, definition)
    db.commit()
    defn = json.loads(wf.definition)
    return WorkflowSummaryRead(
        entity_type=entity_type,
        version=wf.version,
        states=defn.get("states", []),
        transitions=defn.get("transitions", []),
        initial_state=defn.get("initial_state"),
        terminal_states=defn.get("terminal_states", []),
    )


@router.get("/{project_id}/workbench-template")
def get_workbench_template(
    project_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, user_id, PROJECT_ROLES_MANAGE)
    return list(DEFAULT_WORKBENCHES)
