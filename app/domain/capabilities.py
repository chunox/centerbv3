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
HUB_EXPOSURE_MANAGE = "hub.exposure.manage"
DOCUMENT_VIEW_INTERNAL = "document.view.internal"
DOCUMENT_VIEW_PUBLIC = "document.view.public"

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
WORKBENCH_PORTFOLIO = "workbench.portfolio"

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
    CapabilityDef(HUB_DOCUMENT_EDIT, "Editar documento", "hub"),
    CapabilityDef(HUB_EXPOSURE_MANAGE, "Gestionar exposiciones", "hub"),
    CapabilityDef(DOCUMENT_VIEW_INTERNAL, "Ver docs internos", "hub"),
    CapabilityDef(DOCUMENT_VIEW_PUBLIC, "Ver docs públicos", "hub"),
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
    CapabilityDef(WORKBENCH_PORTFOLIO, "Portfolio PM", "workbench"),
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
            SCOPE_FEATURE_CREATE,
            SCOPE_FEATURE_EDIT,
            SCOPE_FEATURE_MIGRATE,
            SCOPE_FEATURE_CANCEL,
            KANBAN_VIEW,
            FEATURE_TRANSITION_CANCELAR,
            FEATURE_TRANSITION_LIBERAR_CLIENTE,
            FEATURE_TRANSITION_RECHAZAR_LIBERACION,
            FEATURE_TRANSITION_COMPLETAR,
            QUERY_CREATE,
            QUERY_SEND,
            QUERY_APPROVE,
            QUERY_CLOSE,
            REPORT_APPROVE,
            REPORT_REJECT,
            HUB_VIEW,
            HUB_PUBLISH,
            HUB_DOCUMENT_EDIT,
            HUB_EXPOSURE_MANAGE,
            DOCUMENT_VIEW_INTERNAL,
            DOCUMENT_VIEW_PUBLIC,
            WORKBENCH_INBOX_PM,
            WORKBENCH_OVERVIEW,
            WORKBENCH_SCOPE,
            WORKBENCH_FEATURES,
            WORKBENCH_KANBAN,
            WORKBENCH_ACTIVITY,
            WORKBENCH_HUB,
            WORKBENCH_TIMELINE,
            WORKBENCH_SETTINGS,
            WORKBENCH_PORTFOLIO,
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
            DOCUMENT_VIEW_INTERNAL,
            DOCUMENT_VIEW_PUBLIC,
            WORKBENCH_INBOX_DEV,
            WORKBENCH_SCOPE,
            WORKBENCH_FEATURES,
            WORKBENCH_KANBAN,
            WORKBENCH_MY_TASKS,
            WORKBENCH_MY_DELIVERIES,
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
            DOCUMENT_VIEW_INTERNAL,
            DOCUMENT_VIEW_PUBLIC,
            WORKBENCH_INBOX_QA,
            WORKBENCH_UAT,
            WORKBENCH_SCOPE,
            WORKBENCH_FEATURES,
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
            DOCUMENT_VIEW_PUBLIC,
            WORKBENCH_INBOX_CLIENT,
            WORKBENCH_SCOPE,
            WORKBENCH_FEATURES,
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
        SCOPE_FEATURE_CREATE,
        SCOPE_FEATURE_EDIT,
        SCOPE_FEATURE_MIGRATE,
        FEATURE_TRANSITION_CANCELAR,
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


def is_valid_capability(key: str) -> bool:
    return key in ALL_CAPABILITY_KEYS


def validate_capability_keys(keys: list[str]) -> list[str]:
    """Devuelve claves inválidas."""
    return [k for k in keys if k not in ALL_CAPABILITY_KEYS]
