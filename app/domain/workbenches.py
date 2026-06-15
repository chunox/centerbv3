"""
Definiciones de workbenches (superficies de trabajo en sidebar).
"""
from __future__ import annotations

from typing import Any

# Vistas legacy retiradas (lista global de features / mis entregas).
DEPRECATED_WORKBENCH_KEYS = frozenset({"features", "my_deliveries"})
DEPRECATED_VIEW_ROUTES = frozenset({"features", "dev/features"})

from app.domain.capabilities import (
    WORKBENCH_ACTIVITY,
    WORKBENCH_HUB,
    WORKBENCH_INBOX_CLIENT,
    WORKBENCH_INBOX_DEV,
    WORKBENCH_INBOX_PM,
    WORKBENCH_INBOX_QA,
    WORKBENCH_KANBAN,
    WORKBENCH_MY_TASKS,
    WORKBENCH_OVERVIEW,
    WORKBENCH_SCOPE,
    WORKBENCH_SETTINGS,
    WORKBENCH_STUDIO,
    WORKBENCH_TEAM,
    WORKBENCH_TIMELINE,
    WORKBENCH_UAT,
)

DEFAULT_WORKBENCHES: list[dict[str, Any]] = [
    # ── PM ───────────────────────────────────────────────────────────────────
    {
        "key": "overview",
        "label": "Resumen",
        "route": "overview",
        "icon": "home",
        "section": "pm",
        "required_capabilities": [WORKBENCH_OVERVIEW],
        "orden": 10,
    },
    {
        "key": "inbox_pm",
        "label": "Bandeja",
        "route": "inbox",
        "icon": "inbox",
        "section": "pm",
        "required_capabilities": [WORKBENCH_INBOX_PM],
        "queue_filter": {
            "entity_types": ["report", "query", "feature"],
            "state_categories": ["inbox_pm", "inbox_shared"],
        },
        "orden": 20,
    },
    {
        "key": "team",
        "label": "Equipo",
        "route": "team",
        "icon": "users-round",
        "section": "pm",
        "required_capabilities": [WORKBENCH_TEAM],
        "orden": 30,
    },
    # ── Desarrollo ────────────────────────────────────────────────────────────
    {
        "key": "inbox_dev",
        "label": "Bandeja",
        "route": "dev/inbox",
        "icon": "terminal",
        "section": "dev",
        "required_capabilities": [WORKBENCH_INBOX_DEV],
        "queue_filter": {
            "entity_types": ["query"],
            "state_categories": ["active", "pending", "inbox_pm", "inbox_client"],
            "created_by_actor": True,
        },
        "orden": 40,
    },
    {
        "key": "kanban",
        "label": "Kanban",
        "route": "kanban",
        "icon": "columns-3",
        "section": "dev",
        "required_capabilities": [WORKBENCH_KANBAN],
        "orden": 50,
    },
    {
        "key": "my_tasks",
        "label": "Mis tareas",
        "route": "dev/my-tasks",
        "icon": "circle-check-big",
        "section": "dev",
        "required_capabilities": [WORKBENCH_MY_TASKS],
        "orden": 60,
    },
    # ── Calidad ──────────────────────────────────────────────────────────────
    {
        "key": "inbox_qa",
        "label": "Bandeja",
        "route": "qa/inbox",
        "icon": "flask-conical",
        "section": "qa",
        "required_capabilities": [WORKBENCH_INBOX_QA],
        "queue_filter": {
            "entity_types": ["query"],
            "state_categories": ["active", "pending", "inbox_pm", "inbox_client"],
            "created_by_actor": True,
        },
        "orden": 70,
    },
    {
        "key": "uat",
        "label": "Validación UAT",
        "route": "qa",
        "icon": "shield-check",
        "section": "qa",
        "required_capabilities": [WORKBENCH_UAT],
        "queue_filter": {"entity_types": ["feature"], "state_categories": ["uat"]},
        "orden": 80,
    },
    # ── Cliente ───────────────────────────────────────────────────────────────
    {
        "key": "inbox_client",
        "label": "Bandeja",
        "route": "client/inbox",
        "icon": "message-circle",
        "section": "client",
        "required_capabilities": [WORKBENCH_INBOX_CLIENT],
        "queue_filter": {
            "entity_types": ["query", "report", "feature"],
            "state_categories": ["inbox_client", "pending", "inbox_shared"],
            "include_states": ["respuesta_cliente", "esperando_validacion_cliente"],
        },
        "orden": 90,
    },
    # ── Planificación ─────────────────────────────────────────────────────────
    # Órdenes 100–120 reservados para ítems Scrum (sprint_board, product_backlog, sprint_planning).
    {
        "key": "scope",
        "label": "Alcance",
        "route": "scope",
        "icon": "layers",
        "section": "plan",
        "required_capabilities": [WORKBENCH_SCOPE],
        "orden": 130,
    },
    {
        "key": "hub",
        "label": "Centro del proyecto",
        "route": "hub",
        "icon": "book-open-text",
        "section": "plan",
        "required_capabilities": [WORKBENCH_HUB],
        "orden": 140,
    },
    {
        "key": "timeline",
        "label": "Cronograma",
        "route": "timeline",
        "icon": "gantt-chart",
        "section": "plan",
        "required_capabilities": [WORKBENCH_TIMELINE],
        "orden": 150,
    },
    {
        "key": "activity",
        "label": "Actividad",
        "route": "activity",
        "icon": "trending-up",
        "section": "plan",
        "required_capabilities": [WORKBENCH_ACTIVITY],
        "orden": 160,
    },
    # ── Administración ────────────────────────────────────────────────────────
    {
        "key": "studio",
        "label": "Studio",
        "route": "studio",
        "icon": "sliders-horizontal",
        "section": "admin",
        "required_capabilities": [WORKBENCH_STUDIO],
        "orden": 170,
    },
    {
        "key": "settings",
        "label": "Configuración",
        "route": "settings",
        "icon": "settings",
        "section": "admin",
        "required_capabilities": [WORKBENCH_SETTINGS],
        "orden": 180,
    },
]

SECTION_LABELS: dict[str, str] = {
    "pm": "PM",
    "dev": "Desarrollo",
    "qa": "Calidad",
    "client": "Cliente",
    "plan": "Planificación",
    "admin": "Administración",
}
