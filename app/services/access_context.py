"""
Assembler del bundle access-context.

Lee pack definitions estáticas + project settings + rol del actor
y construye el payload que el frontend necesita en runtime.

Nunca lee DB para datos de workflow — solo para:
  - El proyecto (pack_slug, template_slug, delivery_mode, settings)
  - Los miembros (para saber el rol del actor)
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.packs.definitions import get_pack, TEMPLATE_TO_PACK
from app.models.entities import Project, ProjectMember, ProjectRole
from app.services.access import get_member_context
from app.schemas.access_context import (
    AccessContextResponse,
    EntityTypeInfoSchema,
    FieldInfoSchema,
    ProjectInfoSchema,
    StateInfoSchema,
    TransitionInfoSchema,
    WorkbenchInfoSchema,
    WorkflowInfoSchema,
)

# Mapa de estado → categoría (para colores en el frontend)
STATE_CATEGORY: dict[str, str] = {
    # Work item states (unified)
    "backlog": "pending",
    "to_do": "pending",
    "in_progress": "active",
    "in_review": "active",
    "done": "done",
    "cancelled": "terminal",
    # Sprint operational states (containers — separate lifecycle)
    "pendiente": "pending",
    "activo": "active",
    "cerrado": "terminal",
    "cancelado": "terminal",
    # Waterfall UAT variant
    "uat": "active",
}

# Etiquetas legibles
STATE_LABELS: dict[str, str] = {
    # Work item states (unified)
    "backlog": "Backlog",
    "to_do": "Por Hacer",
    "in_progress": "En Progreso",
    "in_review": "En Revisión",
    "done": "Completado",
    "cancelled": "Cancelado",
    # Sprint operational states
    "pendiente": "Pendiente",
    "activo": "Activo",
    "cerrado": "Cerrado",
    "cancelado": "Cancelado",
    # Waterfall UAT variant
    "uat": "UAT",
}

# Campos por tipo de record
ENTITY_FIELDS: dict[str, list[FieldInfoSchema]] = {
    "milestone": [
        FieldInfoSchema(key="title", label="Título", type="text"),
        FieldInfoSchema(key="fecha_inicio", label="Inicio", type="date"),
        FieldInfoSchema(key="fecha_fin", label="Fin objetivo", type="date"),
    ],
    "feature": [
        FieldInfoSchema(key="title", label="Título", type="text"),
        FieldInfoSchema(key="estimacion", label="Estimación", type="number"),
        FieldInfoSchema(key="fecha_inicio", label="Inicio", type="date"),
        FieldInfoSchema(key="fecha_fin", label="Fin", type="date"),
    ],
    "task": [
        FieldInfoSchema(key="title", label="Título", type="text"),
        FieldInfoSchema(key="estimacion", label="Estimación", type="number"),
    ],
    "sprint": [
        FieldInfoSchema(key="title", label="Nombre del sprint", type="text"),
        FieldInfoSchema(key="fecha_inicio", label="Inicio", type="date"),
        FieldInfoSchema(key="fecha_fin", label="Fin", type="date"),
    ],
    "product_backlog": [
        FieldInfoSchema(key="title", label="Título", type="text"),
        FieldInfoSchema(key="estimacion", label="Estimación", type="number"),
    ],
}

ENTITY_LABELS: dict[str, str] = {
    "milestone": "Hito",
    "feature": "Feature",
    "task": "Tarea",
    "sprint": "Sprint",
    "product_backlog": "Backlog",
}

ICON_OVERRIDE: dict[str, str] = {
    "dashboard": "LayoutDashboard",
    "layers":    "Layers",
    "kanban":    "Columns2",
    "octagon":   "Octagon",
    "users":     "Users",
    "folder":    "Folder",
    "calendar":  "Calendar",
    "settings":  "Settings",
    "activity":  "Activity",
    "inbox":     "Inbox",
    "git-branch":"GitBranch",
    "flag":      "Flag",
    "layout-dashboard": "LayoutDashboard",
}


def get_actor_role_slug(db: Session, project_id: str, actor_id: str) -> str | None:
    """Devuelve el role_slug del actor en el proyecto o None si no es miembro."""
    result = (
        db.query(ProjectRole.slug)
        .join(ProjectMember, ProjectMember.role_id == ProjectRole.id)
        .filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == actor_id,
        )
        .first()
    )
    return result[0] if result else None


def build_access_context(
    db: Session,
    project: Project,
    actor_id: str,
) -> AccessContextResponse:
    """Ensambla el access-context completo para el par (proyecto, actor)."""
    ctx = get_member_context(db, actor_id, str(project.id))
    role_slug = ctx.role_slug if ctx else None

    # Determinar pack
    pack_key = TEMPLATE_TO_PACK.get(str(project.template_slug), str(project.pack_slug))
    pack = get_pack(pack_key)
    if not pack:
        # Fallback: pack vacío si el template no existe (no debería ocurrir)
        return AccessContextResponse(
            capabilities=[],
            workbenches=[],
            entity_types={},
            workflows={},
            project=ProjectInfoSchema(
                id=str(project.id),
                nombre=project.nombre,
                delivery_mode=project.delivery_mode,
                effort_unit=(project.settings or {}).get("effort_unit", "hours"),
                hours_per_story_point=(project.settings or {}).get("hours_per_story_point", 8.0),
            ),
        )

    # Capabilities según todos los roles del actor (multi-rol)
    capabilities = list(ctx.capabilities) if ctx else []

    # Workbenches para este template + filtrar por capabilities
    template_key = str(project.template_slug)
    raw_workbenches = pack.workbenches_by_template.get(template_key, ())
    cap_set = set(capabilities)

    workbenches = [
        WorkbenchInfoSchema(
            key=w.key,
            label=w.label,
            route=w.route,
            icon=ICON_OVERRIDE.get(w.icon, w.icon),
            section=w.section,
            order=w.order,
            custom_view_key=w.custom_view_key,
        )
        for w in raw_workbenches
        if not w.required_capabilities or any(c in cap_set for c in w.required_capabilities)
    ]

    # Determinar workflow activo (variant si settings lo especifica)
    project_settings: dict = project.settings or {}
    active_workflows: dict[str, WorkflowInfoSchema] = {}
    entity_types: dict[str, EntityTypeInfoSchema] = {}

    for entity_type, wf in pack.workflows.items():
        # Revisar si hay variant activo para este entity_type
        variant_key = project_settings.get(f"{entity_type}_workflow")
        variant_full = f"{entity_type}.{variant_key}" if variant_key else ""
        resolved_wf = pack.workflow_variants.get(variant_full, wf) if variant_key else wf

        from app.services.capability_map import capability_for_transition

        states = [
            StateInfoSchema(
                key=s,
                label=STATE_LABELS.get(s, s.replace("_", " ").title()),
                category=STATE_CATEGORY.get(s, "active"),
            )
            for s in resolved_wf.states
        ]
        transitions = [
            TransitionInfoSchema(
                action_id=t.action_id,
                label=t.label,
                from_states=list(t.from_states),
                to_state=t.to_state,
                required_roles=list(t.required_roles),
                required_capability=capability_for_transition(entity_type, t.action_id),
            )
            for t in resolved_wf.transitions
        ]
        active_workflows[entity_type] = WorkflowInfoSchema(
            entity_type=entity_type,
            states=states,
            transitions=transitions,
        )
        entity_types[entity_type] = EntityTypeInfoSchema(
            label=ENTITY_LABELS.get(entity_type, entity_type),
            states=states,
            fields=ENTITY_FIELDS.get(entity_type, []),
        )

    project_info = ProjectInfoSchema(
        id=str(project.id),
        nombre=project.nombre,
        delivery_mode=str(project.delivery_mode),
        effort_unit=project_settings.get("effort_unit", "hours"),
        hours_per_story_point=float(project_settings.get("hours_per_story_point", 8.0)),
    )

    return AccessContextResponse(
        capabilities=capabilities,
        workbenches=workbenches,
        entity_types=entity_types,
        workflows=active_workflows,
        project=project_info,
        role_slug=role_slug,
        role_slugs=sorted(ctx.role_slugs) if ctx else [],
    )
