"""
PACK_DEFINITIONS — fuente de verdad de packs y workflows.

Inmutable, tipado, en código. Sin copias en DB.
El access-context assembler lee de aquí en cada request.

Para agregar un nuevo pack o workflow variant:
  1. Definí un nuevo PackDef o WorkflowDef
  2. Agregalo a PACK_DEFINITIONS o workflow_variants del pack correspondiente
  3. Creá un template_slug en TEMPLATE_TO_PACK si aplica
"""

from dataclasses import dataclass, field


# ─── Tipos ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TransitionDef:
    action_id: str
    label: str
    from_states: tuple[str, ...]
    to_state: str
    required_roles: tuple[str, ...] = ()
    gates: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowDef:
    entity_type: str
    states: tuple[str, ...]
    initial_state: str
    terminal_states: tuple[str, ...]
    transitions: tuple[TransitionDef, ...]


@dataclass(frozen=True)
class WorkbenchDef:
    key: str
    label: str
    route: str
    icon: str
    section: str          # main | ceremonies | admin
    order: int
    custom_view_key: str
    required_capabilities: tuple[str, ...]


@dataclass(frozen=True)
class PackDef:
    slug: str
    name: str
    delivery_mode: str    # waterfall | scrum
    roles: dict[str, str]                             # slug → nombre
    role_colors: dict[str, str]                       # slug → color hex
    record_types: tuple[str, ...]
    workflows: dict[str, WorkflowDef]
    workflow_variants: dict[str, WorkflowDef]         # "feature.with_uat" etc.
    workbenches_by_template: dict[str, tuple[WorkbenchDef, ...]]
    capabilities_by_role: dict[str, tuple[str, ...]]
    default_settings: dict


# ─── Pack: software-waterfall ────────────────────────────────────────────────

WATERFALL_PACK = PackDef(
    slug="software-waterfall",
    name="Software (Waterfall)",
    delivery_mode="waterfall",
    roles={
        "pm": "Project Manager",
        "tech_lead": "Tech Lead",
        "dev": "Desarrollador",
        "qa": "QA",
    },
    role_colors={
        "pm": "oklch(0.66 0.14 296)",
        "tech_lead": "oklch(0.66 0.14 236)",
        "dev": "oklch(0.66 0.14 158)",
        "qa": "oklch(0.66 0.14 76)",
    },
    record_types=("milestone", "feature", "task"),
    workflows={
        "milestone": WorkflowDef(
            entity_type="milestone",
            states=("backlog", "in_progress", "done", "cancelled"),
            initial_state="backlog",
            terminal_states=("done", "cancelled"),
            transitions=(
                TransitionDef("iniciar", "Iniciar", ("backlog",), "in_progress",
                    required_roles=("pm", "tech_lead")),
                TransitionDef("completar", "Completar", ("in_progress",), "done",
                    required_roles=("pm", "tech_lead"),
                    side_effects=("sync_from_features",)),
                TransitionDef("cancelar", "Cancelar", ("backlog", "in_progress"), "cancelled",
                    required_roles=("pm",)),
            ),
        ),
        "feature": WorkflowDef(
            entity_type="feature",
            states=("backlog", "in_progress", "in_review", "done", "cancelled"),
            initial_state="backlog",
            terminal_states=("done", "cancelled"),
            transitions=(
                TransitionDef("iniciar", "Iniciar", ("backlog",), "in_progress",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked",)),
                TransitionDef("revisar", "Mover a revisión", ("in_progress",), "in_review",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked",)),
                TransitionDef("completar", "Completar", ("in_review",), "done",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked",),
                    side_effects=("sync_parent_milestone",)),
                TransitionDef("cancelar", "Cancelar", ("backlog", "in_progress", "in_review"), "cancelled",
                    required_roles=("pm", "tech_lead")),
            ),
        ),
        "task": WorkflowDef(
            entity_type="task",
            states=("backlog", "to_do", "in_progress", "in_review", "done", "cancelled"),
            initial_state="backlog",
            terminal_states=("done", "cancelled"),
            transitions=(
                TransitionDef("move_to_todo", "Mover a Por Hacer", ("backlog",), "to_do",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked", "dependency_satisfied")),
                TransitionDef("start", "Iniciar", ("to_do",), "in_progress",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked", "dependency_satisfied")),
                TransitionDef("review", "Mover a revisión", ("in_progress",), "in_review",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked",)),
                TransitionDef("complete", "Completar", ("in_review",), "done",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked",),
                    side_effects=("sync_parent_feature",)),
                TransitionDef("cancel", "Cancelar", ("backlog", "to_do", "in_progress", "in_review"), "cancelled",
                    required_roles=("pm", "tech_lead")),
            ),
        ),
    },
    workflow_variants={
        # MVP2: disponible pero no expuesto en UI hasta configuración
        "feature.with_uat": WorkflowDef(
            entity_type="feature",
            states=("backlog", "in_progress", "in_review", "uat", "done", "cancelled"),
            initial_state="backlog",
            terminal_states=("done", "cancelled"),
            transitions=(
                TransitionDef("iniciar", "Iniciar", ("backlog",), "in_progress",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked",)),
                TransitionDef("revisar", "Mover a revisión", ("in_progress",), "in_review",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked",)),
                TransitionDef("pasar_a_uat", "Pasar a UAT", ("in_review",), "uat",
                    required_roles=("pm", "tech_lead"),
                    gates=("not_blocked",)),
                TransitionDef("aprobar_uat", "Aprobar UAT", ("uat",), "done",
                    required_roles=("pm",),
                    gates=("not_blocked",),
                    side_effects=("sync_parent_milestone",)),
                TransitionDef("rechazar_uat", "Rechazar — volver a revisión", ("uat",), "in_review",
                    required_roles=("pm",)),
                TransitionDef("cancelar", "Cancelar", ("backlog", "in_progress", "in_review", "uat"), "cancelled",
                    required_roles=("pm", "tech_lead")),
            ),
        ),
    },
    workbenches_by_template={
        "t3_interno_clasico": (
            WorkbenchDef("overview",  "Resumen",       "overview",  "LayoutDashboard", "main",  10, "software.overview",       ("workbench.overview",)),
            WorkbenchDef("scope",     "Alcance",       "scope",     "Layers",          "main",  20, "software.scope_waterfall", ("workbench.scope",)),
            WorkbenchDef("kanban",    "Kanban",        "kanban",    "Kanban",          "main",  30, "software.kanban",          ("workbench.kanban",)),
            WorkbenchDef("blocked",   "Bloqueados",    "blocked",   "Octagon",         "main",  40, "generic.blocked",         ("workbench.blocked",)),
            WorkbenchDef("team",      "Equipo",        "team",      "Users",           "main",  50, "generic.team",            ("workbench.team",)),
            WorkbenchDef("hub",       "Hub",           "hub",       "Folder",          "main",  60, "generic.hub",             ("workbench.hub",)),
            WorkbenchDef("activity",  "Actividad",     "activity",  "Activity",        "main",  70, "generic.activity",        ("workbench.activity",)),
            WorkbenchDef("settings",  "Configuración", "settings",  "Settings",        "admin", 100, "generic.settings",       ("workbench.settings",)),
        ),
    },
    capabilities_by_role={
        "pm": (
            "record.milestone.create", "record.milestone.edit", "record.milestone.delete",
            "record.milestone.transition.iniciar", "record.milestone.transition.completar",
            "record.milestone.transition.cancelar",
            "record.feature.create", "record.feature.edit", "record.feature.delete",
            "record.feature.transition.iniciar", "record.feature.transition.revisar",
            "record.feature.transition.completar", "record.feature.transition.cancelar",
            "record.task.create", "record.task.edit", "record.task.delete",
            "record.task.transition.move", "record.task.transition.cancel",
            "blocker.create", "blocker.resolve",
            "dependency.create", "dependency.delete",
            "member.add", "member.remove",
            "workbench.overview", "workbench.scope", "workbench.kanban",
            "workbench.blocked", "workbench.team", "workbench.hub",
            "workbench.activity", "workbench.settings",
        ),
        "tech_lead": (
            "record.milestone.transition.iniciar", "record.milestone.transition.completar",
            "record.feature.create", "record.feature.edit",
            "record.feature.transition.iniciar", "record.feature.transition.revisar",
            "record.feature.transition.completar", "record.feature.transition.cancelar",
            "record.task.create", "record.task.edit",
            "record.task.transition.move", "record.task.transition.cancel",
            "blocker.create", "blocker.resolve",
            "dependency.create", "dependency.delete",
            "workbench.overview", "workbench.scope", "workbench.kanban",
            "workbench.blocked", "workbench.team", "workbench.hub", "workbench.activity",
        ),
        "dev": (
            "record.task.create", "record.task.edit",
            "record.task.transition.move",
            "record.feature.transition.iniciar", "record.feature.transition.revisar",
            "record.feature.transition.completar",
            "blocker.create",
            "dependency.create",
            "workbench.overview", "workbench.scope", "workbench.kanban",
            "workbench.blocked", "workbench.hub", "workbench.activity",
        ),
        "qa": (
            "record.task.create", "record.task.edit",
            "record.task.transition.move",
            "record.feature.transition.revisar", "record.feature.transition.completar",
            "blocker.create",
            "workbench.overview", "workbench.kanban",
            "workbench.blocked", "workbench.hub", "workbench.activity",
        ),
        "cliente": (
            # Solo lectura: overview, bloqueantes y hub
            "workbench.overview", "workbench.blocked", "workbench.hub",
        ),
    },
    default_settings={
        "effort_unit": "hours",
        "hours_per_story_point": 6,
        "feature_workflow": "simple",
    },
)


# ─── Pack: software-scrum ────────────────────────────────────────────────────

SCRUM_PACK = PackDef(
    slug="software-scrum",
    name="Software (Scrum)",
    delivery_mode="scrum",
    roles={
        "pm": "Product Owner",
        "tech_lead": "Scrum Master",
        "dev": "Developer",
        "qa": "QA",
    },
    role_colors={
        "pm": "oklch(0.66 0.14 296)",
        "tech_lead": "oklch(0.66 0.14 236)",
        "dev": "oklch(0.66 0.14 158)",
        "qa": "oklch(0.66 0.14 76)",
    },
    record_types=("sprint", "product_backlog", "task"),
    workflows={
        "sprint": WorkflowDef(
            entity_type="sprint",
            states=("pendiente", "activo", "cerrado", "cancelado"),
            initial_state="pendiente",
            terminal_states=("cerrado", "cancelado"),
            transitions=(
                TransitionDef("activar", "Activar sprint", ("pendiente",), "activo",
                    required_roles=("pm", "tech_lead")),
                TransitionDef("cerrar", "Cerrar sprint", ("activo",), "cerrado",
                    required_roles=("pm", "tech_lead"),
                    side_effects=("handle_incomplete_stories",)),
                TransitionDef("cancelar", "Cancelar sprint", ("pendiente", "activo"), "cancelado",
                    required_roles=("pm",)),
            ),
        ),
        # Épicas — scrum_role=epic
        "epic": WorkflowDef(
            entity_type="epic",
            states=("backlog", "in_progress", "done", "cancelled"),
            initial_state="backlog",
            terminal_states=("done", "cancelled"),
            transitions=(
                TransitionDef("iniciar", "Iniciar épica", ("backlog",), "in_progress",
                    required_roles=("pm", "tech_lead")),
                TransitionDef("completar", "Completar épica", ("in_progress",), "done",
                    required_roles=("pm", "tech_lead")),
                TransitionDef("cancelar", "Cancelar épica", ("backlog", "in_progress"), "cancelled",
                    required_roles=("pm",)),
            ),
        ),
        # Historias — scrum_role=story
        "story": WorkflowDef(
            entity_type="story",
            states=("backlog", "to_do", "in_progress", "in_review", "done", "cancelled"),
            initial_state="backlog",
            terminal_states=("done", "cancelled"),
            transitions=(
                TransitionDef("comprometer", "Comprometer al sprint", ("backlog",), "to_do",
                    required_roles=("pm", "tech_lead"),
                    side_effects=("reparent_to_sprint",)),
                TransitionDef("iniciar", "Iniciar", ("to_do",), "in_progress",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked",)),
                TransitionDef("revisar", "Mover a revisión", ("in_progress",), "in_review",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked",)),
                TransitionDef("completar", "Completar historia", ("in_review",), "done",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked",),
                    side_effects=("rollup_to_epic",)),
                TransitionDef("devolver", "Devolver al backlog", ("to_do", "in_progress", "in_review"), "backlog",
                    required_roles=("pm", "tech_lead"),
                    side_effects=("reparent_to_backlog",)),
                TransitionDef("cancelar", "Cancelar", ("backlog", "to_do", "in_progress", "in_review"), "cancelled",
                    required_roles=("pm",)),
            ),
        ),
        # Dev tasks — scrum_role=dev
        "dev_task": WorkflowDef(
            entity_type="dev_task",
            states=("backlog", "to_do", "in_progress", "in_review", "done", "cancelled"),
            initial_state="backlog",
            terminal_states=("done", "cancelled"),
            transitions=(
                TransitionDef("move_to_todo", "Por Hacer", ("backlog",), "to_do",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked", "dependency_satisfied")),
                TransitionDef("start", "Iniciar", ("to_do",), "in_progress",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked", "dependency_satisfied")),
                TransitionDef("review", "Mover a revisión", ("in_progress",), "in_review",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked",)),
                TransitionDef("complete", "Completar", ("in_review",), "done",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    gates=("not_blocked",),
                    side_effects=("rollup_to_story",)),
                TransitionDef("cancel", "Cancelar", ("backlog", "to_do", "in_progress", "in_review"), "cancelled",
                    required_roles=("pm", "tech_lead")),
            ),
        ),
        # Subtareas — scrum_role=subtask (mismo flujo que dev_task)
        "subtask": WorkflowDef(
            entity_type="subtask",
            states=("backlog", "to_do", "in_progress", "done", "cancelled"),
            initial_state="backlog",
            terminal_states=("done", "cancelled"),
            transitions=(
                TransitionDef("start", "Iniciar", ("backlog", "to_do"), "in_progress",
                    required_roles=("pm", "tech_lead", "dev", "qa")),
                TransitionDef("complete", "Completar", ("in_progress",), "done",
                    required_roles=("pm", "tech_lead", "dev", "qa"),
                    side_effects=("rollup_to_dev_task",)),
                TransitionDef("cancel", "Cancelar", ("backlog", "to_do", "in_progress"), "cancelled",
                    required_roles=("pm", "tech_lead")),
            ),
        ),
    },
    workflow_variants={},
    workbenches_by_template={
        "t6_scrum_interno": (
            WorkbenchDef("overview",        "Resumen",         "overview",        "LayoutDashboard", "main",       10, "software.scrum_overview",  ("workbench.overview",)),
            WorkbenchDef("product_backlog", "Product Backlog", "product_backlog", "List",            "main",       20, "software.product_backlog", ("workbench.product_backlog",)),
            WorkbenchDef("sprint_planning", "Sprint Planning", "sprint_planning", "Calendar",        "main",       30, "software.sprint_planning", ("workbench.sprint_planning",)),
            WorkbenchDef("sprint_board",    "Sprint Board",    "sprint_board",    "Kanban",          "main",       40, "software.sprint_board",    ("workbench.sprint_board",)),
            WorkbenchDef("scrum_kanban",    "Kanban",          "kanban",          "Columns2",        "main",       50, "software.scrum_kanban",    ("workbench.kanban",)),
            WorkbenchDef("scrum_scope",     "Alcance",         "scope",           "Layers",          "main",       60, "software.scope_scrum",     ("workbench.scope",)),
            WorkbenchDef("blocked",         "Bloqueados",      "blocked",         "Octagon",         "main",       70, "software.scrum_blockers",  ("workbench.blocked",)),
            WorkbenchDef("team",            "Equipo",          "team",            "Users",           "main",       80, "generic.team",             ("workbench.team",)),
            WorkbenchDef("hub",             "Hub",             "hub",             "Folder",          "main",       90, "generic.hub",              ("workbench.hub",)),
            WorkbenchDef("activity",        "Actividad",       "activity",        "Activity",        "main",      100, "generic.activity",         ("workbench.activity",)),
            WorkbenchDef("planning_cer",    "Planning",        "scrum/planning",  "Play",      "ceremonies", 10, "software.scrum_planning",  ("workbench.ceremonies",)),
            WorkbenchDef("daily_cer",       "Daily",           "scrum/daily",     "Sun",       "ceremonies", 20, "software.scrum_daily",     ("workbench.ceremonies",)),
            WorkbenchDef("retro_cer",       "Retro",           "scrum/retro",     "RotateCcw", "ceremonies", 30, "software.scrum_retro",     ("workbench.ceremonies",)),
            WorkbenchDef("settings",        "Configuración",   "settings",        "Settings",  "admin",     100, "generic.settings",         ("workbench.settings",)),
        ),
        # t7: mismo que t6 + rol cliente (vista reducida)
        "t7_scrum_cliente": (
            WorkbenchDef("overview",        "Resumen",         "overview",        "LayoutDashboard", "main",       10, "software.scrum_overview",  ("workbench.overview",)),
            WorkbenchDef("product_backlog", "Product Backlog", "product_backlog", "List",            "main",       20, "software.product_backlog", ("workbench.product_backlog",)),
            WorkbenchDef("sprint_planning", "Sprint Planning", "sprint_planning", "Calendar",        "main",       30, "software.sprint_planning", ("workbench.sprint_planning",)),
            WorkbenchDef("sprint_board",    "Sprint Board",    "sprint_board",    "Kanban",          "main",       40, "software.sprint_board",    ("workbench.sprint_board",)),
            WorkbenchDef("scrum_kanban",    "Kanban",          "kanban",          "Columns2",        "main",       50, "software.scrum_kanban",    ("workbench.kanban",)),
            WorkbenchDef("scrum_scope",     "Alcance",         "scope",           "Layers",          "main",       60, "software.scope_scrum",     ("workbench.scope",)),
            WorkbenchDef("blocked",         "Bloqueados",      "blocked",         "Octagon",         "main",       70, "software.scrum_blockers",  ("workbench.blocked",)),
            WorkbenchDef("hub",             "Hub",             "hub",             "Folder",          "main",       80, "generic.hub",              ("workbench.hub",)),
            WorkbenchDef("settings",        "Configuración",   "settings",        "Settings",  "admin",     100, "generic.settings",         ("workbench.settings",)),
        ),
    },
    capabilities_by_role={
        "pm": (
            "sprint.create", "sprint.transition.activar", "sprint.transition.cerrar", "sprint.transition.cancelar",
            "record.epic.create", "record.epic.edit", "record.epic.transition.iniciar",
            "record.epic.transition.completar", "record.epic.transition.cancelar",
            "record.story.create", "record.story.edit", "record.story.delete",
            "record.story.transition.comprometer", "record.story.transition.iniciar",
            "record.story.transition.revisar", "record.story.transition.completar",
            "record.story.transition.devolver", "record.story.transition.cancelar",
            "record.dev_task.create", "record.dev_task.edit",
            "record.dev_task.transition.move", "record.dev_task.transition.cancel",
            "record.subtask.create", "record.subtask.edit",
            "record.subtask.transition.start", "record.subtask.transition.complete",
            "blocker.create", "blocker.resolve",
            "dependency.create", "dependency.delete",
            "member.add", "member.remove",
            "ceremony.create", "ceremony.start", "ceremony.close",
            "workbench.overview", "workbench.product_backlog", "workbench.sprint_planning",
            "workbench.sprint_board", "workbench.kanban", "workbench.scope",
            "workbench.blocked", "workbench.team", "workbench.hub",
            "workbench.activity", "workbench.ceremonies", "workbench.settings",
        ),
        "tech_lead": (
            "sprint.transition.activar", "sprint.transition.cerrar",
            "record.epic.create", "record.epic.transition.iniciar", "record.epic.transition.completar",
            "record.story.create", "record.story.edit",
            "record.story.transition.comprometer", "record.story.transition.iniciar",
            "record.story.transition.revisar", "record.story.transition.completar",
            "record.story.transition.devolver", "record.story.transition.cancelar",
            "record.dev_task.create", "record.dev_task.edit",
            "record.dev_task.transition.move", "record.dev_task.transition.cancel",
            "record.subtask.create", "record.subtask.edit",
            "record.subtask.transition.start", "record.subtask.transition.complete",
            "blocker.create", "blocker.resolve",
            "dependency.create",
            "ceremony.create", "ceremony.start", "ceremony.close",
            "workbench.overview", "workbench.product_backlog", "workbench.sprint_planning",
            "workbench.sprint_board", "workbench.kanban", "workbench.scope",
            "workbench.blocked", "workbench.team", "workbench.hub",
            "workbench.activity", "workbench.ceremonies",
        ),
        "dev": (
            "record.story.transition.iniciar", "record.story.transition.revisar", "record.story.transition.completar",
            "record.dev_task.create", "record.dev_task.edit", "record.dev_task.transition.move",
            "record.subtask.create", "record.subtask.edit",
            "record.subtask.transition.start", "record.subtask.transition.complete",
            "blocker.create", "dependency.create",
            "workbench.overview", "workbench.sprint_board", "workbench.kanban",
            "workbench.blocked", "workbench.hub", "workbench.activity", "workbench.ceremonies",
        ),
        "qa": (
            "record.story.transition.revisar", "record.story.transition.completar",
            "record.dev_task.transition.move",
            "blocker.create",
            "workbench.overview", "workbench.sprint_board", "workbench.kanban",
            "workbench.blocked", "workbench.hub", "workbench.activity", "workbench.ceremonies",
        ),
        "cliente": (
            "workbench.overview", "workbench.blocked", "workbench.hub",
        ),
    },
    default_settings={
        "effort_unit": "story_points",
        "hours_per_story_point": 6,
    },
)


# ─── Registro central ────────────────────────────────────────────────────────

PACK_DEFINITIONS: dict[str, PackDef] = {
    "software-waterfall": WATERFALL_PACK,
    "software-scrum": SCRUM_PACK,
}

# Mapeo template_slug → pack_slug (para creación de proyectos)
TEMPLATE_TO_PACK: dict[str, str] = {
    "t3_interno_clasico": "software-waterfall",
    "t6_scrum_interno":   "software-scrum",
    "t7_scrum_cliente":   "software-scrum",
}

# Delivery mode por template
TEMPLATE_DELIVERY_MODE: dict[str, str] = {
    "t3_interno_clasico": "waterfall",
    "t6_scrum_interno":   "scrum",
    "t7_scrum_cliente":   "scrum",
}


def get_pack(pack_slug: str) -> PackDef:
    pack = PACK_DEFINITIONS.get(pack_slug)
    if not pack:
        raise ValueError(f"Pack desconocido: {pack_slug}")
    return pack


def get_workflow(pack_slug: str, entity_type: str, project_settings: dict) -> WorkflowDef:
    """
    Retorna el WorkflowDef activo para un entity_type en un proyecto.
    Si el proyecto tiene un variant activo en settings, lo retorna en lugar del default.
    """
    pack = get_pack(pack_slug)

    # Verificar si hay un variant activo en settings del proyecto
    variant_key = f"{entity_type}_workflow"
    active_variant = project_settings.get(variant_key)
    if active_variant and active_variant != "simple":
        full_key = f"{entity_type}.{active_variant}"
        variant = pack.workflow_variants.get(full_key)
        if variant:
            return variant

    workflow = pack.workflows.get(entity_type)
    if not workflow:
        raise ValueError(f"No hay workflow para '{entity_type}' en el pack '{pack_slug}'")
    return workflow
