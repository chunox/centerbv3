"""
Catálogo canónico de capacidades de Center v3.

Los roles custom por proyecto solo combinan claves de este catálogo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CapabilityGroup = Literal[
    "project",
    "scope",
    "kanban",
    "feature",
    "query",
    "report",
    "hub",
    "workbench",
    "audit",
    "roles",
]


@dataclass(frozen=True, slots=True)
class CapabilityDef:
    key: str
    label: str
    group: CapabilityGroup
    description: str = ""


# ── Proyecto ──────────────────────────────────────────────────────────────

PROJECT_SETTINGS_EDIT = "project.settings.edit"
PROJECT_MEMBERS_MANAGE = "project.members.manage"
PROJECT_LIFECYCLE_MANAGE = "project.lifecycle.manage"
PROJECT_ROLES_MANAGE = "project.roles.manage"

# ── Alcance ───────────────────────────────────────────────────────────────

SCOPE_MILESTONE_CREATE = "scope.milestone.create"
SCOPE_MILESTONE_EDIT = "scope.milestone.edit"
SCOPE_MILESTONE_REORDER = "scope.milestone.reorder"
SCOPE_MILESTONE_CANCEL = "scope.milestone.cancel"
SCOPE_MILESTONE_DELETE = "scope.milestone.delete"

SCOPE_SPRINT_CREATE = "scope.sprint.create"
SCOPE_SPRINT_EDIT = "scope.sprint.edit"
SCOPE_SPRINT_REORDER = "scope.sprint.reorder"
SCOPE_SPRINT_CANCEL = "scope.sprint.cancel"
SCOPE_SPRINT_DELETE = "scope.sprint.delete"
SCOPE_EPIC_CREATE = "scope.epic.create"
SCOPE_EPIC_EDIT = "scope.epic.edit"
SCOPE_EPIC_REORDER = "scope.epic.reorder"
SCOPE_EPIC_CANCEL = "scope.epic.cancel"
SCOPE_EPIC_DELETE = "scope.epic.delete"
SCOPE_FEATURE_CREATE = "scope.feature.create"
SCOPE_FEATURE_EDIT = "scope.feature.edit"
SCOPE_FEATURE_MIGRATE = "scope.feature.migrate"
SCOPE_FEATURE_CANCEL = "scope.feature.cancel"

# ── Kanban ────────────────────────────────────────────────────────────────

KANBAN_VIEW = "kanban.view"
KANBAN_TASK_CREATE = "kanban.task.create"
KANBAN_TASK_EDIT = "kanban.task.edit"
KANBAN_TASK_MOVE = "kanban.task.move"
KANBAN_TASK_CANCEL = "kanban.task.cancel"
KANBAN_TASK_ASSIGN = "kanban.task.assign"

# ── Feature transitions (workflow-linked) ─────────────────────────────────

FEATURE_TRANSITION_PASAR_A_UAT = "feature.transition.pasar_a_uat"
FEATURE_TRANSITION_CANCELAR = "feature.transition.cancelar"
FEATURE_TRANSITION_ENVIAR_AL_PM = "feature.transition.enviar_al_pm"
FEATURE_TRANSITION_DEVOLVER_REWORK = "feature.transition.devolver_rework"
FEATURE_TRANSITION_LIBERAR_CLIENTE = "feature.transition.liberar_cliente"
FEATURE_TRANSITION_RECHAZAR_LIBERACION = "feature.transition.rechazar_liberacion"
FEATURE_TRANSITION_CONFIRMAR = "feature.transition.confirmar"
FEATURE_TRANSITION_NO_FUNCIONA = "feature.transition.no_funciona"
FEATURE_TRANSITION_COMPLETAR = "feature.transition.completar"
FEATURE_TRANSITION_COMPROMETER_SPRINT = "feature.transition.comprometer_sprint"
FEATURE_TRANSITION_VOLVER_BACKLOG = "feature.transition.volver_backlog"

FEATURE_TRANSITION_KEYS = frozenset(
    {
        FEATURE_TRANSITION_PASAR_A_UAT,
        FEATURE_TRANSITION_CANCELAR,
        FEATURE_TRANSITION_ENVIAR_AL_PM,
        FEATURE_TRANSITION_DEVOLVER_REWORK,
        FEATURE_TRANSITION_LIBERAR_CLIENTE,
        FEATURE_TRANSITION_RECHAZAR_LIBERACION,
        FEATURE_TRANSITION_CONFIRMAR,
        FEATURE_TRANSITION_NO_FUNCIONA,
        FEATURE_TRANSITION_COMPLETAR,
        FEATURE_TRANSITION_COMPROMETER_SPRINT,
        FEATURE_TRANSITION_VOLVER_BACKLOG,
    }
)

# ── Historia Scrum (workflow-linked; record SQL = task) ─────────────────────

SCOPE_STORY_CREATE = "scope.story.create"
SCOPE_STORY_EDIT = "scope.story.edit"
SCOPE_STORY_CANCEL = "scope.story.cancel"

STORY_TRANSITION_PASAR_A_UAT = "story.transition.pasar_a_uat"
STORY_TRANSITION_CANCELAR = "story.transition.cancelar"
STORY_TRANSITION_ENVIAR_AL_PM = "story.transition.enviar_al_pm"
STORY_TRANSITION_DEVOLVER_REWORK = "story.transition.devolver_rework"
STORY_TRANSITION_LIBERAR_CLIENTE = "story.transition.liberar_cliente"
STORY_TRANSITION_RECHAZAR_LIBERACION = "story.transition.rechazar_liberacion"
STORY_TRANSITION_CONFIRMAR = "story.transition.confirmar"
STORY_TRANSITION_NO_FUNCIONA = "story.transition.no_funciona"
STORY_TRANSITION_COMPLETAR = "story.transition.completar"
STORY_TRANSITION_COMPROMETER_SPRINT = "story.transition.comprometer_sprint"
STORY_TRANSITION_VOLVER_BACKLOG = "story.transition.volver_backlog"

STORY_TRANSITION_KEYS = frozenset(
    {
        STORY_TRANSITION_PASAR_A_UAT,
        STORY_TRANSITION_CANCELAR,
        STORY_TRANSITION_ENVIAR_AL_PM,
        STORY_TRANSITION_DEVOLVER_REWORK,
        STORY_TRANSITION_LIBERAR_CLIENTE,
        STORY_TRANSITION_RECHAZAR_LIBERACION,
        STORY_TRANSITION_CONFIRMAR,
        STORY_TRANSITION_NO_FUNCIONA,
        STORY_TRANSITION_COMPLETAR,
        STORY_TRANSITION_COMPROMETER_SPRINT,
        STORY_TRANSITION_VOLVER_BACKLOG,
    }
)

# ── Consultas ─────────────────────────────────────────────────────────────

QUERY_CREATE = "query.create"
QUERY_SEND = "query.send"
QUERY_APPROVE = "query.approve"
QUERY_RESPOND = "query.respond"
QUERY_CLOSE = "query.close"

# ── Reportes ──────────────────────────────────────────────────────────────

REPORT_CREATE = "report.create"
REPORT_APPROVE = "report.approve"
REPORT_REJECT = "report.reject"

# ── Hub ───────────────────────────────────────────────────────────────────

HUB_VIEW = "hub.view"
HUB_PUBLISH = "hub.publish"
HUB_DOCUMENT_EDIT = "hub.document.edit"

# ── Workbenches ───────────────────────────────────────────────────────────

WORKBENCH_INBOX_PM = "workbench.inbox.pm"
WORKBENCH_INBOX_DEV = "workbench.inbox.dev"
WORKBENCH_INBOX_QA = "workbench.inbox.qa"
WORKBENCH_INBOX_CLIENT = "workbench.inbox.client"
WORKBENCH_UAT = "workbench.uat"
WORKBENCH_OVERVIEW = "workbench.overview"
WORKBENCH_SCOPE = "workbench.scope"
WORKBENCH_FEATURES = "workbench.features"
WORKBENCH_KANBAN = "workbench.kanban"
WORKBENCH_MY_TASKS = "workbench.my_tasks"
WORKBENCH_MY_DELIVERIES = "workbench.my_deliveries"
WORKBENCH_ACTIVITY = "workbench.activity"
WORKBENCH_HUB = "workbench.hub"
WORKBENCH_TIMELINE = "workbench.timeline"
WORKBENCH_SETTINGS = "workbench.settings"
WORKBENCH_STUDIO = "workbench.studio"
WORKBENCH_PORTFOLIO = "workbench.portfolio"
WORKBENCH_TEAM = "workbench.team"
WORKBENCH_SPRINT_BOARD    = "workbench.sprint_board"
WORKBENCH_PRODUCT_BACKLOG = "workbench.product_backlog"
WORKBENCH_SPRINT_PLANNING = "workbench.sprint_planning"
WORKBENCH_SCRUM_IMPEDIMENTS = "workbench.scrum_impediments"
WORKBENCH_SCRUM_REFINEMENT = "workbench.scrum_refinement"
WORKBENCH_SCRUM_CAPACITY = "workbench.scrum_capacity"
WORKBENCH_SCRUM_METRICS = "workbench.scrum_metrics"

# ── Auditoría ─────────────────────────────────────────────────────────────

AUDIT_VIEW_ALL = "audit.view.all"
AUDIT_VIEW_SCOPED = "audit.view.scoped"
TIMELINE_VIEW = "timeline.view"

# ── Comentarios / adjuntos ────────────────────────────────────────────────

COMMENT_CREATE = "comment.create"
ATTACHMENT_UPLOAD = "attachment.upload"

CAPABILITY_CATALOG: tuple[CapabilityDef, ...] = (
    CapabilityDef(PROJECT_SETTINGS_EDIT, "Editar proyecto", "project"),
    CapabilityDef(PROJECT_MEMBERS_MANAGE, "Gestionar miembros", "project"),
    CapabilityDef(PROJECT_LIFECYCLE_MANAGE, "Cerrar/reabrir/cancelar proyecto", "project"),
    CapabilityDef(PROJECT_ROLES_MANAGE, "Configurar roles y workflows", "roles"),
    CapabilityDef(SCOPE_MILESTONE_CREATE, "Crear hitos", "scope"),
    CapabilityDef(SCOPE_MILESTONE_EDIT, "Editar hitos", "scope"),
    CapabilityDef(SCOPE_MILESTONE_REORDER, "Reordenar hitos", "scope"),
    CapabilityDef(SCOPE_MILESTONE_CANCEL, "Cancelar hitos", "scope"),
    CapabilityDef(SCOPE_MILESTONE_DELETE, "Eliminar hitos", "scope"),
    CapabilityDef(SCOPE_SPRINT_CREATE, "Crear sprints", "scope"),
    CapabilityDef(SCOPE_SPRINT_EDIT, "Editar sprints", "scope"),
    CapabilityDef(SCOPE_SPRINT_REORDER, "Reordenar sprints", "scope"),
    CapabilityDef(SCOPE_SPRINT_CANCEL, "Cancelar sprints", "scope"),
    CapabilityDef(SCOPE_SPRINT_DELETE, "Eliminar sprints", "scope"),
    CapabilityDef(SCOPE_EPIC_CREATE, "Crear épicas", "scope"),
    CapabilityDef(SCOPE_EPIC_EDIT, "Editar épicas", "scope"),
    CapabilityDef(SCOPE_EPIC_REORDER, "Reordenar épicas", "scope"),
    CapabilityDef(SCOPE_EPIC_CANCEL, "Cancelar épicas", "scope"),
    CapabilityDef(SCOPE_EPIC_DELETE, "Eliminar épicas", "scope"),
    CapabilityDef(SCOPE_FEATURE_CREATE, "Crear features", "scope"),
    CapabilityDef(SCOPE_FEATURE_EDIT, "Editar features", "scope"),
    CapabilityDef(SCOPE_FEATURE_MIGRATE, "Migrar features", "scope"),
    CapabilityDef(SCOPE_FEATURE_CANCEL, "Cancelar features", "scope"),
    CapabilityDef(KANBAN_VIEW, "Ver Kanban", "kanban"),
    CapabilityDef(KANBAN_TASK_CREATE, "Crear tareas", "kanban"),
    CapabilityDef(KANBAN_TASK_EDIT, "Editar tareas", "kanban"),
    CapabilityDef(KANBAN_TASK_MOVE, "Mover tareas", "kanban"),
    CapabilityDef(KANBAN_TASK_CANCEL, "Cancelar tareas", "kanban"),
    CapabilityDef(KANBAN_TASK_ASSIGN, "Asignar tareas", "kanban"),
    CapabilityDef(FEATURE_TRANSITION_PASAR_A_UAT, "Pasar feature a UAT", "feature"),
    CapabilityDef(FEATURE_TRANSITION_CANCELAR, "Cancelar feature", "feature"),
    CapabilityDef(FEATURE_TRANSITION_ENVIAR_AL_PM, "Enviar UAT al PM", "feature"),
    CapabilityDef(FEATURE_TRANSITION_DEVOLVER_REWORK, "Devolver rework", "feature"),
    CapabilityDef(FEATURE_TRANSITION_LIBERAR_CLIENTE, "Liberar al cliente", "feature"),
    CapabilityDef(
        FEATURE_TRANSITION_RECHAZAR_LIBERACION, "Rechazar liberación", "feature"
    ),
    CapabilityDef(FEATURE_TRANSITION_CONFIRMAR, "Confirmar entrega", "feature"),
    CapabilityDef(FEATURE_TRANSITION_NO_FUNCIONA, "Rechazar entrega", "feature"),
    CapabilityDef(FEATURE_TRANSITION_COMPLETAR, "Completar feature", "feature"),
    CapabilityDef(FEATURE_TRANSITION_COMPROMETER_SPRINT, "Comprometer historia al sprint", "feature"),
    CapabilityDef(FEATURE_TRANSITION_VOLVER_BACKLOG, "Devolver historia al backlog", "feature"),
    CapabilityDef(SCOPE_STORY_CREATE, "Crear historias", "scope"),
    CapabilityDef(SCOPE_STORY_EDIT, "Editar historias", "scope"),
    CapabilityDef(SCOPE_STORY_CANCEL, "Cancelar historias", "scope"),
    CapabilityDef(STORY_TRANSITION_PASAR_A_UAT, "Pasar historia a UAT", "feature"),
    CapabilityDef(STORY_TRANSITION_CANCELAR, "Cancelar historia", "feature"),
    CapabilityDef(STORY_TRANSITION_ENVIAR_AL_PM, "Enviar UAT al PM (historia)", "feature"),
    CapabilityDef(STORY_TRANSITION_DEVOLVER_REWORK, "Devolver rework (historia)", "feature"),
    CapabilityDef(STORY_TRANSITION_LIBERAR_CLIENTE, "Liberar historia al cliente", "feature"),
    CapabilityDef(STORY_TRANSITION_RECHAZAR_LIBERACION, "Rechazar liberación (historia)", "feature"),
    CapabilityDef(STORY_TRANSITION_CONFIRMAR, "Confirmar entrega (historia)", "feature"),
    CapabilityDef(STORY_TRANSITION_NO_FUNCIONA, "Rechazar entrega (historia)", "feature"),
    CapabilityDef(STORY_TRANSITION_COMPLETAR, "Completar historia", "feature"),
    CapabilityDef(STORY_TRANSITION_COMPROMETER_SPRINT, "Comprometer historia al sprint", "feature"),
    CapabilityDef(STORY_TRANSITION_VOLVER_BACKLOG, "Devolver historia al backlog", "feature"),
    CapabilityDef(QUERY_CREATE, "Crear consultas", "query"),
    CapabilityDef(QUERY_SEND, "Enviar consultas", "query"),
    CapabilityDef(QUERY_APPROVE, "Aprobar envío consulta", "query"),
    CapabilityDef(QUERY_RESPOND, "Responder consultas", "query"),
    CapabilityDef(QUERY_CLOSE, "Cerrar consultas", "query"),
    CapabilityDef(REPORT_CREATE, "Crear reportes", "report"),
    CapabilityDef(REPORT_APPROVE, "Aprobar reportes", "report"),
    CapabilityDef(REPORT_REJECT, "Rechazar reportes", "report"),
    CapabilityDef(HUB_VIEW, "Ver hub", "hub"),
    CapabilityDef(HUB_PUBLISH, "Publicar en hub", "hub"),
    CapabilityDef(HUB_DOCUMENT_EDIT, "Editar contenido hub", "hub"),
    CapabilityDef(WORKBENCH_INBOX_PM, "Bandeja PM", "workbench"),
    CapabilityDef(WORKBENCH_INBOX_DEV, "Bandeja Dev", "workbench"),
    CapabilityDef(WORKBENCH_INBOX_QA, "Bandeja QA", "workbench"),
    CapabilityDef(WORKBENCH_INBOX_CLIENT, "Bandeja Cliente", "workbench"),
    CapabilityDef(WORKBENCH_UAT, "Validación UAT", "workbench"),
    CapabilityDef(WORKBENCH_OVERVIEW, "Resumen PM", "workbench"),
    CapabilityDef(WORKBENCH_SCOPE, "Alcance", "workbench"),
    CapabilityDef(WORKBENCH_FEATURES, "Features global", "workbench"),
    CapabilityDef(WORKBENCH_KANBAN, "Kanban", "workbench"),
    CapabilityDef(WORKBENCH_MY_TASKS, "Mis tareas", "workbench"),
    CapabilityDef(WORKBENCH_MY_DELIVERIES, "Mis entregas", "workbench"),
    CapabilityDef(WORKBENCH_ACTIVITY, "Actividad", "workbench"),
    CapabilityDef(WORKBENCH_HUB, "Centro del proyecto", "workbench"),
    CapabilityDef(WORKBENCH_TIMELINE, "Cronograma", "workbench"),
    CapabilityDef(WORKBENCH_SETTINGS, "Configuración", "workbench"),
    CapabilityDef(WORKBENCH_STUDIO, "Studio", "workbench"),
    CapabilityDef(WORKBENCH_PORTFOLIO, "Portfolio PM", "workbench"),
    CapabilityDef(WORKBENCH_TEAM, "Vista Equipo PM", "workbench"),
    CapabilityDef(WORKBENCH_SPRINT_BOARD, "Sprint Board (Scrum)", "workbench"),
    CapabilityDef(WORKBENCH_PRODUCT_BACKLOG, "Product Backlog (Scrum)", "workbench"),
    CapabilityDef(WORKBENCH_SPRINT_PLANNING, "Sprint Planning (Scrum)", "workbench"),
    CapabilityDef(WORKBENCH_SCRUM_IMPEDIMENTS, "Impedimentos (Scrum)", "workbench"),
    CapabilityDef(WORKBENCH_SCRUM_REFINEMENT, "Refinement (Scrum)", "workbench"),
    CapabilityDef(WORKBENCH_SCRUM_CAPACITY, "Capacity (Scrum)", "workbench"),
    CapabilityDef(WORKBENCH_SCRUM_METRICS, "Métricas (Scrum)", "workbench"),
    CapabilityDef(AUDIT_VIEW_ALL, "Ver toda la auditoría", "audit"),
    CapabilityDef(AUDIT_VIEW_SCOPED, "Ver auditoría acotada", "audit"),
    CapabilityDef(TIMELINE_VIEW, "Ver cronograma", "audit"),
    CapabilityDef(COMMENT_CREATE, "Comentar", "project"),
    CapabilityDef(ATTACHMENT_UPLOAD, "Subir adjuntos", "project"),
)

ALL_CAPABILITY_KEYS: frozenset[str] = frozenset(c.key for c in CAPABILITY_CATALOG)

CAPABILITY_BY_KEY: dict[str, CapabilityDef] = {c.key: c for c in CAPABILITY_CATALOG}

# Mapeo legacy rol → capacidades (para backfill y compatibilidad)
LEGACY_ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "pm": frozenset(
        {
            PROJECT_SETTINGS_EDIT,
            PROJECT_MEMBERS_MANAGE,
            PROJECT_LIFECYCLE_MANAGE,
            PROJECT_ROLES_MANAGE,
            SCOPE_MILESTONE_CREATE,
            SCOPE_MILESTONE_EDIT,
            SCOPE_MILESTONE_REORDER,
            SCOPE_MILESTONE_CANCEL,
            SCOPE_MILESTONE_DELETE,
            SCOPE_SPRINT_CREATE,
            SCOPE_SPRINT_EDIT,
            SCOPE_SPRINT_REORDER,
            SCOPE_SPRINT_CANCEL,
            SCOPE_SPRINT_DELETE,
            SCOPE_EPIC_CREATE,
            SCOPE_EPIC_EDIT,
            SCOPE_EPIC_REORDER,
            SCOPE_EPIC_CANCEL,
            SCOPE_EPIC_DELETE,
            SCOPE_FEATURE_CREATE,
            SCOPE_FEATURE_EDIT,
            SCOPE_FEATURE_MIGRATE,
            SCOPE_FEATURE_CANCEL,
            KANBAN_VIEW,
            FEATURE_TRANSITION_CANCELAR,
            FEATURE_TRANSITION_LIBERAR_CLIENTE,
            FEATURE_TRANSITION_RECHAZAR_LIBERACION,
            FEATURE_TRANSITION_COMPLETAR,
            FEATURE_TRANSITION_COMPROMETER_SPRINT,
            FEATURE_TRANSITION_VOLVER_BACKLOG,
            SCOPE_STORY_CREATE,
            SCOPE_STORY_EDIT,
            SCOPE_STORY_CANCEL,
            STORY_TRANSITION_CANCELAR,
            STORY_TRANSITION_LIBERAR_CLIENTE,
            STORY_TRANSITION_RECHAZAR_LIBERACION,
            STORY_TRANSITION_COMPLETAR,
            STORY_TRANSITION_COMPROMETER_SPRINT,
            STORY_TRANSITION_VOLVER_BACKLOG,
            QUERY_CREATE,
            QUERY_SEND,
            QUERY_APPROVE,
            QUERY_CLOSE,
            REPORT_APPROVE,
            REPORT_REJECT,
            HUB_VIEW,
            HUB_PUBLISH,
            HUB_DOCUMENT_EDIT,
            WORKBENCH_INBOX_PM,
            WORKBENCH_OVERVIEW,
            WORKBENCH_SCOPE,
            WORKBENCH_KANBAN,
            WORKBENCH_ACTIVITY,
            WORKBENCH_HUB,
            WORKBENCH_TIMELINE,
            WORKBENCH_SETTINGS,
            WORKBENCH_STUDIO,
            WORKBENCH_PORTFOLIO,
            WORKBENCH_TEAM,
            WORKBENCH_SPRINT_BOARD,
            WORKBENCH_PRODUCT_BACKLOG,
            WORKBENCH_SPRINT_PLANNING,
            WORKBENCH_SCRUM_IMPEDIMENTS,
            WORKBENCH_SCRUM_REFINEMENT,
            WORKBENCH_SCRUM_CAPACITY,
            WORKBENCH_SCRUM_METRICS,
            AUDIT_VIEW_ALL,
            TIMELINE_VIEW,
            COMMENT_CREATE,
            ATTACHMENT_UPLOAD,
        }
    ),
    "dev": frozenset(
        {
            SCOPE_FEATURE_EDIT,
            KANBAN_VIEW,
            KANBAN_TASK_CREATE,
            KANBAN_TASK_EDIT,
            KANBAN_TASK_MOVE,
            KANBAN_TASK_CANCEL,
            KANBAN_TASK_ASSIGN,
            FEATURE_TRANSITION_PASAR_A_UAT,
            QUERY_CREATE,
            QUERY_SEND,
            HUB_VIEW,
            HUB_PUBLISH,
            WORKBENCH_INBOX_DEV,
            WORKBENCH_SCOPE,
    WORKBENCH_KANBAN,
    WORKBENCH_MY_TASKS,
    WORKBENCH_SPRINT_BOARD,
            WORKBENCH_ACTIVITY,
            WORKBENCH_HUB,
            WORKBENCH_TIMELINE,
            AUDIT_VIEW_SCOPED,
            TIMELINE_VIEW,
            COMMENT_CREATE,
            ATTACHMENT_UPLOAD,
        }
    ),
    "qa": frozenset(
        {
            FEATURE_TRANSITION_ENVIAR_AL_PM,
            FEATURE_TRANSITION_DEVOLVER_REWORK,
            QUERY_CREATE,
            QUERY_SEND,
            HUB_VIEW,
            WORKBENCH_INBOX_QA,
            WORKBENCH_UAT,
            WORKBENCH_SCOPE,
            WORKBENCH_SPRINT_BOARD,
            WORKBENCH_ACTIVITY,
            WORKBENCH_HUB,
            WORKBENCH_TIMELINE,
            AUDIT_VIEW_SCOPED,
            TIMELINE_VIEW,
            COMMENT_CREATE,
            ATTACHMENT_UPLOAD,
        }
    ),
    "cliente": frozenset(
        {
            FEATURE_TRANSITION_CONFIRMAR,
            FEATURE_TRANSITION_NO_FUNCIONA,
            QUERY_RESPOND,
            REPORT_CREATE,
            HUB_VIEW,
            WORKBENCH_INBOX_CLIENT,
            WORKBENCH_SCOPE,
            WORKBENCH_ACTIVITY,
            WORKBENCH_HUB,
            WORKBENCH_TIMELINE,
            AUDIT_VIEW_SCOPED,
            TIMELINE_VIEW,
            COMMENT_CREATE,
            ATTACHMENT_UPLOAD,
        }
    ),
}

TECH_LEAD_CAPABILITIES: frozenset[str] = (
    LEGACY_ROLE_CAPABILITIES["dev"]
    | {
        SCOPE_MILESTONE_CREATE,
        SCOPE_MILESTONE_EDIT,
        SCOPE_MILESTONE_REORDER,
        SCOPE_SPRINT_CREATE,
        SCOPE_SPRINT_EDIT,
        SCOPE_SPRINT_REORDER,
        SCOPE_SPRINT_CANCEL,
        SCOPE_FEATURE_CREATE,
        SCOPE_FEATURE_EDIT,
        SCOPE_FEATURE_MIGRATE,
        FEATURE_TRANSITION_CANCELAR,
        FEATURE_TRANSITION_COMPROMETER_SPRINT,
        SCOPE_STORY_CREATE,
        SCOPE_STORY_EDIT,
        STORY_TRANSITION_CANCELAR,
        STORY_TRANSITION_COMPROMETER_SPRINT,
        STORY_TRANSITION_PASAR_A_UAT,
        WORKBENCH_PRODUCT_BACKLOG,
        WORKBENCH_SPRINT_PLANNING,
        WORKBENCH_SCRUM_IMPEDIMENTS,
        WORKBENCH_SCRUM_REFINEMENT,
        WORKBENCH_SCRUM_CAPACITY,
        WORKBENCH_SCRUM_METRICS,
    }
)

PM_TECNICO_CAPABILITIES: frozenset[str] = (
    LEGACY_ROLE_CAPABILITIES["pm"] | LEGACY_ROLE_CAPABILITIES["dev"]
)

TEMPLATE_ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    **LEGACY_ROLE_CAPABILITIES,
    "tech_lead": TECH_LEAD_CAPABILITIES,
    "pm_tecnico": PM_TECNICO_CAPABILITIES,
}

TEMPLATE_ROLE_LABELS: dict[str, str] = {
    "pm": "PM",
    "dev": "Dev",
    "qa": "QA",
    "cliente": "Cliente",
    "tech_lead": "Tech Líder",
    "pm_tecnico": "PM Técnico",
}


WORKBENCH_BOARD = "workbench.board"
WORKBENCH_GANTT = "workbench.gantt"
WORKBENCH_TIMELINE = "workbench.timeline"
WORKBENCH_CHECKLIST = "workbench.checklist"
WORKBENCH_INBOX_GENERIC = "workbench.inbox"

GENERIC_WORKBENCH_CAPS = frozenset(
    {
        WORKBENCH_BOARD,
        WORKBENCH_GANTT,
        WORKBENCH_TIMELINE,
        WORKBENCH_CHECKLIST,
        WORKBENCH_INBOX_GENERIC,
    }
)


def is_record_capability(key: str) -> bool:
    return key.startswith("record.")


def is_valid_capability(key: str) -> bool:
    if key in ALL_CAPABILITY_KEYS or key in GENERIC_WORKBENCH_CAPS:
        return True
    if is_record_capability(key):
        parts = key.split(".")
        if len(parts) >= 4 and parts[-2] == "transition":
            return True
        return len(parts) >= 3 and parts[-1] in ("read", "create", "edit", "delete")
    return False


def validate_capability_keys(keys: list[str]) -> list[str]:
    """Devuelve claves inválidas."""
    return [k for k in keys if not is_valid_capability(k)]


_LEGACY_TRANSITION_PREFIX = "feature.transition."
_STORY_TRANSITION_PREFIX = "story.transition."


def resolve_capability_keys(keys: list[str]) -> list[str]:
    """Expande alias legacy ↔ record para autorización."""
    expanded: list[str] = []
    for key in keys:
        expanded.append(key)
        if key.startswith(_STORY_TRANSITION_PREFIX):
            action = key[len(_STORY_TRANSITION_PREFIX) :]
            expanded.append(f"record.task.transition.{action}")
            expanded.append(f"{_LEGACY_TRANSITION_PREFIX}{action}")
        elif key.startswith(_LEGACY_TRANSITION_PREFIX):
            action = key[len(_LEGACY_TRANSITION_PREFIX) :]
            expanded.append(f"record.feature.transition.{action}")
            expanded.append(f"{_STORY_TRANSITION_PREFIX}{action}")
        elif key.startswith("record.feature.transition."):
            action = key.split(".")[-1]
            expanded.append(f"{_LEGACY_TRANSITION_PREFIX}{action}")
        elif key.startswith("scope.milestone."):
            expanded.append(key.replace("scope.milestone.", "record.milestone.", 1))
            ms_suffix = key.split("scope.milestone.", 1)[1]
            if ms_suffix in ("create", "edit", "reorder", "cancel", "delete"):
                expanded.append("record.milestone.read")
        elif key.startswith("scope.sprint."):
            expanded.append(key.replace("scope.sprint.", "record.sprint.", 1))
            sp_suffix = key.split("scope.sprint.", 1)[1]
            if sp_suffix in ("create", "edit", "reorder", "cancel", "delete"):
                expanded.append("record.sprint.read")
        elif key.startswith("scope.epic."):
            expanded.append(key.replace("scope.epic.", "record.epic.", 1))
            epic_suffix = key.split("scope.epic.", 1)[1]
            if epic_suffix in ("create", "edit", "reorder", "cancel", "delete"):
                expanded.append("record.epic.read")
        elif key.startswith("record.epic.") and key.count(".") >= 2:
            suffix = key.split("record.epic.", 1)[1]
            if suffix in ("create", "edit", "reorder", "cancel", "delete", "read"):
                expanded.append(f"scope.epic.{suffix}" if suffix != "read" else "scope.epic.create")
        elif key.startswith("record.milestone.") and key.count(".") >= 2:
            suffix = key.split("record.milestone.", 1)[1]
            expanded.append(f"scope.milestone.{suffix}")
        elif key.startswith("record.sprint.") and key.count(".") >= 2:
            suffix = key.split("record.sprint.", 1)[1]
            expanded.append(f"scope.sprint.{suffix}")
        elif key.startswith("scope.feature."):
            expanded.append(key.replace("scope.feature.", "record.feature.", 1))
            feat_suffix = key.split("scope.feature.", 1)[1]
            if feat_suffix in ("create", "edit", "migrate", "cancel"):
                expanded.append("record.feature.read")
            if feat_suffix == "create":
                expanded.append(SCOPE_STORY_CREATE)
        elif key.startswith("scope.story."):
            expanded.append(key.replace("scope.story.", "record.task.", 1))
            story_suffix = key.split("scope.story.", 1)[1]
            if story_suffix in ("create", "edit", "cancel"):
                expanded.append("record.task.read")
            if story_suffix == "create":
                expanded.append(SCOPE_FEATURE_CREATE)
                expanded.append("record.feature.read")
        elif key.startswith("record.feature.") and not key.startswith("record.feature.transition."):
            suffix = key.split("record.feature.", 1)[1]
            if suffix in ("create", "edit", "migrate", "cancel", "read", "delete"):
                expanded.append(f"scope.feature.{suffix}")
        elif key.startswith("kanban.task."):
            suffix = key.split("kanban.task.", 1)[1]
            expanded.append(f"record.task.{suffix}")
            if suffix in ("move", "cancel"):
                expanded.append(f"record.task.transition.{suffix}")
        elif key.startswith("record.task.") and not key.startswith("record.task.transition."):
            suffix = key.split("record.task.", 1)[1]
            if suffix in ("create", "edit", "move", "cancel", "assign", "read"):
                expanded.append(f"kanban.task.{suffix}")
        elif key == WORKBENCH_FEATURES:
            expanded.append("record.feature.read")
        elif key == WORKBENCH_MY_DELIVERIES:
            expanded.append("record.feature.read")
        elif key == WORKBENCH_SCOPE:
            expanded.extend(
                ["record.milestone.read", "record.epic.read", "record.feature.read"]
            )
        elif key == KANBAN_VIEW:
            expanded.append("record.task.read")
        elif key == "record.task.read":
            expanded.append(KANBAN_VIEW)
        elif key == KANBAN_TASK_MOVE:
            expanded.extend(["record.task.transition.move", "record.task.move", key])
        elif key == KANBAN_TASK_CANCEL:
            expanded.extend(["record.task.transition.cancel", "record.task.cancel", key])
        elif key.startswith("query."):
            expanded.append(key.replace("query.", "record.query.", 1))
            expanded.append("record.query.read")
        elif key.startswith("record.query."):
            suffix = key.split("record.query.", 1)[1]
            expanded.append(f"query.{suffix}")
            if suffix != "read":
                expanded.append("record.query.read")
        elif key.startswith("report."):
            expanded.append(key.replace("report.", "record.report.", 1))
            expanded.append("record.report.read")
        elif key.startswith("record.report."):
            suffix = key.split("record.report.", 1)[1]
            expanded.append(f"report.{suffix}")
            if suffix != "read":
                expanded.append("record.report.read")
        elif key == WORKBENCH_INBOX_PM:
            expanded.extend(
                ["record.report.read", "record.query.read", "record.feature.read"]
            )
        elif key == WORKBENCH_INBOX_CLIENT:
            expanded.extend(
                ["record.report.read", "record.query.read", "record.feature.read"]
            )
        elif key == WORKBENCH_INBOX_DEV:
            expanded.extend(["record.query.read", "record.feature.read", "record.task.read"])
        elif key == WORKBENCH_INBOX_QA:
            expanded.extend(["record.feature.read", "record.task.read"])
    return list(dict.fromkeys(expanded))


def expand_nav_capabilities(caps: frozenset[str]) -> frozenset[str]:
    """Caps extra para ítems de menú admin (compat proyectos existentes)."""
    expanded = set(resolve_capability_keys(list(caps)))
    if WORKBENCH_SETTINGS in caps:
        expanded.add(WORKBENCH_STUDIO)
    if PROJECT_ROLES_MANAGE in caps:
        expanded.update({WORKBENCH_STUDIO, WORKBENCH_SETTINGS})
    return frozenset(expanded)
