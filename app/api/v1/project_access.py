"""API de contexto de acceso, roles y workflows por proyecto."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth_deps import AuthContext, get_optional_auth
from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.domain.capabilities import CAPABILITY_CATALOG, CapabilityDef, expand_nav_capabilities
from app.domain.workbenches import DEFAULT_WORKBENCHES, DEPRECATED_VIEW_ROUTES, DEPRECATED_WORKBENCH_KEYS, SECTION_LABELS
from app.schemas.communication_rules import (
    CommunicationRulesRead,
    CommunicationRulesUpdate,
    CommunicationSimulateRead,
    CommunicationSimulateRequest,
)
from app.services.access import assert_member_of_project
from app.services.communication.engine import CommunicationContext, simulate_communication_rules
from app.services.communication.store import (
    get_communication_rules,
    update_communication_rules,
)
from app.services.config_snapshots import list_config_snapshots
from app.services.studio_health import build_studio_health
from app.domain.project_templates import project_tipo_for_project, template_slug_for_legacy_tipo
from app.domain.workflow_templates import workflow_for_template
from app.services.project_profile import list_project_role_slugs
from app.models.entities import ProjectMember, ProjectRole, ProjectWorkflowDefinition
from app.schemas.access_context import (
    CapabilityDefRead,
    EntityTypeRead,
    FieldDefinitionRead,
    PackContextRead,
    ProjectAccessContextRead,
    ProjectBlockRead,
    ProjectRoleCapabilitiesUpdate,
    ProjectRoleCreate,
    ProjectRoleRead,
    ProjectViewRead,
    ProjectWorkbenchesUpdate,
    ProjectWorkflowUpdate,
    RecordTypeRead,
    WorkflowTemplateApply,
    WorkbenchRead,
    WorkflowSummaryRead,
    workflow_summary_from_definition,
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
from app.services.blocks import list_project_blocks, list_project_views
from app.services.packs import (
    get_project_pack_manifest,
    import_project_pack_config,
    list_field_definitions,
    list_record_types,
)
from app.services.records.registry import registry
from app.services.workflow.store import (
    WORKFLOW_ENTITY_TYPES,
    admin_views_from_defaults,
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
    raw_caps = get_effective_capabilities(db, project.id, effective_user)
    caps = sorted(expand_nav_capabilities(raw_caps))

    workflows: dict[str, WorkflowSummaryRead] = {}
    for entity_type in workflow_entity_types(db, project.id):
        defn = get_active_workflow(db, project.id, entity_type)
        if defn is None:
            continue
        version = get_active_workflow_version(db, project.id, entity_type) or 1
        workflows[entity_type] = workflow_summary_from_definition(
            entity_type, version, defn
        )

    wb_raw = get_workbenches(db, project.id)
    visible_workbenches: list[WorkbenchRead] = []
    cap_set = set(caps)
    for wb in sorted(wb_raw, key=lambda w: w.get("orden", 0)):
        if wb.get("key") in DEPRECATED_WORKBENCH_KEYS:
            continue
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
                    custom_view_key=wb.get("custom_view_key"),
                    required_capabilities=required,
                    queue_filter=wb.get("queue_filter"),
                    orden=wb.get("orden", 0),
                    nav_group=wb.get("nav_group"),
                    nav_group_label=wb.get("nav_group_label"),
                    nav_group_order=wb.get("nav_group_order", 0),
                    nav_primary=wb.get("nav_primary", True),
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
        record_types.append(
            RecordTypeRead(
                key=rt.key,
                label=rt.label,
                field_schema=rt.field_schema or [],
                parent_types=rt.parent_types or [],
                icon=rt.icon,
                traits=rt.traits or {},
                is_system=rt.is_system,
                orden=rt.orden,
            )
        )

    entity_types = [EntityTypeRead(**rt.model_dump()) for rt in record_types]

    field_defs = [
        FieldDefinitionRead(
            entity_type_key=fd.entity_type_key,
            field_key=fd.field_key,
            label=fd.label,
            field_type=fd.field_type,
            config=fd.config or {},
            orden=fd.orden,
            is_system=fd.is_system,
        )
        for fd in list_field_definitions(db, project.id)
    ]

    blocks = [
        ProjectBlockRead(
            key=b.key,
            block_slug=b.block_slug,
            label=b.label,
            config=b.config or {},
            enabled=b.enabled,
            orden=b.orden,
        )
        for b in list_project_blocks(db, project.id)
    ]

    views = [
        ProjectViewRead(
            key=v.key,
            label=v.label,
            route=v.route,
            icon=v.icon,
            section=v.section,
            layout=v.layout or {},
            required_capabilities=v.required_capabilities or [],
            orden=v.orden,
        )
        for v in list_project_views(db, project.id)
        if v.key not in DEPRECATED_WORKBENCH_KEYS and v.route not in DEPRECATED_VIEW_ROUTES
    ]
    existing_view_keys = {v.key for v in views}
    for extra in admin_views_from_defaults(existing_view_keys):
        views.append(ProjectViewRead(**extra))
    views.sort(key=lambda v: v.orden)

    return ProjectAccessContextRead(
        user_id=effective_user,
        roles=[_role_to_read(db, r) for r in assignments],
        capabilities=caps,
        workflows=workflows,
        workbenches=visible_workbenches,
        capability_catalog=catalog,
        pack=pack_ctx,
        record_types=record_types,
        entity_types=entity_types,
        field_definitions=field_defs,
        blocks=blocks,
        views=views,
        pack_slug=project.pack_slug,
        template_slug=project.template_slug or "default",
        project_tipo=project_tipo_for_project(project),
        project_role_slugs=list_project_role_slugs(db, project.id),
    member_role_slugs=[r.slug for r in assignments],
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
    comm_rules = get_communication_rules(db, project.id)
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
        "communication_rules": [r.model_dump() for r in comm_rules],
        "record_types": [
            {
                "key": rt.key,
                "label": rt.label,
                "field_schema": rt.field_schema or [],
                "parent_types": rt.parent_types or [],
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
    wf, capabilities_added = update_workflow_definition(db, project, entity_type, payload.definition)
    db.commit()
    return workflow_summary_from_definition(
        entity_type, wf.version, wf.definition, capabilities_added=capabilities_added
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
            view_type=wb.get("view_type", "custom"),
            entity_type=wb.get("entity_type"),
            custom_view_key=wb.get("custom_view_key"),
            required_capabilities=wb.get("required_capabilities", []),
            queue_filter=wb.get("queue_filter"),
            orden=wb.get("orden", 0),
        )
        for wb in payload.workbenches
    ]


@router.get("/{project_id}/communication-rules", response_model=CommunicationRulesRead)
def get_project_communication_rules(
    project_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_member_of_project(db, project.id, user_id)
    rules = get_communication_rules(db, project.id)
    return CommunicationRulesRead(project_id=project.id, rules=rules)


@router.put("/{project_id}/communication-rules", response_model=CommunicationRulesRead)
def put_project_communication_rules(
    project_id: UUID,
    payload: CommunicationRulesUpdate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, payload.actor_user_id, PROJECT_ROLES_MANAGE)
    rules = update_communication_rules(
        db, project, payload.rules, actor_user_id=payload.actor_user_id
    )
    db.commit()
    return CommunicationRulesRead(project_id=project.id, rules=rules)


@router.post(
    "/{project_id}/communication-rules/simulate",
    response_model=CommunicationSimulateRead,
)
def simulate_project_communication_rules(
    project_id: UUID,
    payload: CommunicationSimulateRequest,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, payload.actor_user_id, PROJECT_ROLES_MANAGE)
    from app.models.entities import ProjectRecord

    record = db.get(ProjectRecord, payload.entity_id) if payload.entity_id else None
    ctx = CommunicationContext(
        event=payload.event,
        project=project,
        author_id=payload.actor_user_id,
        entity_type=payload.entity_type or (record.record_type if record else None),
        record_type=payload.record_type,
        entity_id=payload.entity_id,
        action_id=payload.action_id,
        from_state=payload.from_state,
        to_state=payload.to_state,
        comment_entity_type=payload.comment_entity_type,
        record=record,
        sandbox=payload.sandbox,
    )
    matched = simulate_communication_rules(db, ctx)
    return CommunicationSimulateRead(
        matched=[
            {
                "rule_id": m.rule_id,
                "recipient_ids": m.recipient_ids,
                "notification_tipo": m.notification_tipo,
                "deep_link": m.deep_link,
            }
            for m in matched
        ]
    )


@router.get("/{project_id}/studio-health")
def get_studio_health(
    project_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, user_id, PROJECT_ROLES_MANAGE)
    return build_studio_health(db, project)


@router.get("/{project_id}/config-snapshots")
def get_config_snapshots(
    project_id: UUID,
    user_id: UUID,
    kind: str | None = None,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, user_id, PROJECT_ROLES_MANAGE)
    rows = list_config_snapshots(db, project.id, kind=kind)  # type: ignore[arg-type]
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "created_at": r.created_at,
            "created_by": str(r.created_by) if r.created_by else None,
        }
        for r in rows
    ]


@router.post("/{project_id}/config-snapshots/{snapshot_id}/restore", status_code=204)
def restore_config_snapshot(
    project_id: UUID,
    snapshot_id: UUID,
    actor_user_id: UUID,
    db: Session = Depends(get_db),
):
    from app.models.entities import ProjectConfigSnapshot
    from app.schemas.communication_rules import CommunicationRule

    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, PROJECT_ROLES_MANAGE)
    row = db.get(ProjectConfigSnapshot, snapshot_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Snapshot no encontrado")
    payload = row.payload
    if row.kind == "communication":
        rules = [CommunicationRule.model_validate(r) for r in payload]
        update_communication_rules(db, project, rules, actor_user_id=actor_user_id)
    db.commit()


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
    template_slug = project.template_slug or "default"
    if project.pack_slug != "software":
        raise HTTPException(
            status_code=422,
            detail="Plantillas de workflow solo aplican al pack software",
        )
    return workflow_for_template(template_slug, entity_type)


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
    if payload.template_slug:
        template_slug = payload.template_slug
    elif payload.project_tipo:
        template_slug = template_slug_for_legacy_tipo(payload.project_tipo)
    else:
        template_slug = project.template_slug or "default"
    if project.pack_slug != "software":
        raise HTTPException(
            status_code=422,
            detail="Plantillas de workflow solo aplican al pack software",
        )
    definition = workflow_for_template(template_slug, entity_type)
    wf, _capabilities_added = update_workflow_definition(db, project, entity_type, definition)
    db.commit()
    return workflow_summary_from_definition(
        entity_type, wf.version, wf.definition, capabilities_added=_capabilities_added
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
