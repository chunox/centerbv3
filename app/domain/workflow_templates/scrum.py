"""Workflows Scrum (t6-t7)."""
from __future__ import annotations

import copy
from typing import Any

from app.domain.workflow_templates._common import _COND_HAS_CLIENTE, _COND_NO_CLIENTE, _QUERY_BLOCK_GATE, _state
from app.domain.workflow_templates.waterfall import default_feature_workflow_con_cliente
from app.domain.capabilities import (
    FEATURE_TRANSITION_CANCELAR,
    FEATURE_TRANSITION_COMPLETAR,
    FEATURE_TRANSITION_COMPROMETER_SPRINT,
    FEATURE_TRANSITION_CONFIRMAR,
    FEATURE_TRANSITION_DEVOLVER_REWORK,
    FEATURE_TRANSITION_ENVIAR_AL_PM,
    FEATURE_TRANSITION_LIBERAR_CLIENTE,
    FEATURE_TRANSITION_NO_FUNCIONA,
    FEATURE_TRANSITION_PASAR_A_UAT,
    FEATURE_TRANSITION_RECHAZAR_LIBERACION,
    FEATURE_TRANSITION_VOLVER_BACKLOG,
    KANBAN_TASK_CANCEL,
    KANBAN_TASK_MOVE,
    SCOPE_SPRINT_CANCEL,
    STORY_TRANSITION_CANCELAR,
    STORY_TRANSITION_COMPLETAR,
    STORY_TRANSITION_COMPROMETER_SPRINT,
    STORY_TRANSITION_CONFIRMAR,
    STORY_TRANSITION_DEVOLVER_REWORK,
    STORY_TRANSITION_ENVIAR_AL_PM,
    STORY_TRANSITION_LIBERAR_CLIENTE,
    STORY_TRANSITION_NO_FUNCIONA,
    STORY_TRANSITION_PASAR_A_UAT,
    STORY_TRANSITION_RECHAZAR_LIBERACION,
    STORY_TRANSITION_VOLVER_BACKLOG,
)

def default_feature_workflow_scrum_base() -> dict[str, Any]:
    """Scrum: igual que con_cliente pero con product_backlog como estado inicial."""
    wf = copy.deepcopy(default_feature_workflow_con_cliente())
    wf["states"] = [
        _state("product_backlog", "Product Backlog", category="draft", badge="muted"),
        *wf["states"],
    ]
    wf["initial_state"] = "product_backlog"
    transitions = []
    for t in wf["transitions"]:
        if t["id"] == "cancelar":
            t = {**t, "from": ["product_backlog", *t["from"]]}
        transitions.append(t)
    transitions = [
        {
            "id": "comprometer_sprint",
            "label": "Comprometer al Sprint",
            "from": ["product_backlog"],
            "to": "pendiente",
            "required_capabilities": [FEATURE_TRANSITION_COMPROMETER_SPRINT],
            "side_effects": [
                {
                    "type": "set_field",
                    "field_key": "sprint_id",
                    "value_from_context": "sprint_id",
                },
                {"type": "sync_scrum_sprint_dates"},
            ],
        },
        *transitions,
        {
            "id": "volver_al_backlog",
            "label": "Volver al Product Backlog",
            "from": ["pendiente"],
            "to": "product_backlog",
            "required_capabilities": [FEATURE_TRANSITION_VOLVER_BACKLOG],
            "side_effects": [{"type": "clear_field", "field_key": "sprint_id"}],
        },
    ]
    wf["transitions"] = transitions
    return wf


def default_feature_workflow_scrum_interno() -> dict[str, Any]:
    wf = default_feature_workflow_scrum_base()
    wf["transitions"] = [
        t for t in wf["transitions"]
        if t["id"] not in ("liberar_cliente", "confirmar", "no_funciona")
    ]
    wf["transitions"].append(
        {
            "id": "completar",
            "label": "Completar",
            "from": ["esperando_liberacion_pm"],
            "to": "completado",
            "required_capabilities": [FEATURE_TRANSITION_COMPLETAR],
            "conditions": [_COND_NO_CLIENTE],
            "gates": [_QUERY_BLOCK_GATE],
        }
    )
    return wf


def default_feature_workflow_scrum_cliente() -> dict[str, Any]:
    return default_feature_workflow_scrum_base()


def _map_feature_caps_to_story(wf: dict[str, Any]) -> dict[str, Any]:
    """Reemplaza caps feature.transition.* por story.transition.* en workflow Scrum."""
    mapping = {
        FEATURE_TRANSITION_PASAR_A_UAT: STORY_TRANSITION_PASAR_A_UAT,
        FEATURE_TRANSITION_CANCELAR: STORY_TRANSITION_CANCELAR,
        FEATURE_TRANSITION_ENVIAR_AL_PM: STORY_TRANSITION_ENVIAR_AL_PM,
        FEATURE_TRANSITION_DEVOLVER_REWORK: STORY_TRANSITION_DEVOLVER_REWORK,
        FEATURE_TRANSITION_LIBERAR_CLIENTE: STORY_TRANSITION_LIBERAR_CLIENTE,
        FEATURE_TRANSITION_RECHAZAR_LIBERACION: STORY_TRANSITION_RECHAZAR_LIBERACION,
        FEATURE_TRANSITION_CONFIRMAR: STORY_TRANSITION_CONFIRMAR,
        FEATURE_TRANSITION_NO_FUNCIONA: STORY_TRANSITION_NO_FUNCIONA,
        FEATURE_TRANSITION_COMPLETAR: STORY_TRANSITION_COMPLETAR,
        FEATURE_TRANSITION_COMPROMETER_SPRINT: STORY_TRANSITION_COMPROMETER_SPRINT,
        FEATURE_TRANSITION_VOLVER_BACKLOG: STORY_TRANSITION_VOLVER_BACKLOG,
    }
    out = copy.deepcopy(wf)
    for transition in out.get("transitions", []):
        caps = transition.get("required_capabilities") or []
        transition["required_capabilities"] = [mapping.get(c, c) for c in caps]
    return out


def default_task_workflow_scrum_story_base() -> dict[str, Any]:
    """Historia Scrum: flujo kanban-native (sin UAT / PM / validación cliente)."""
    from app.domain.workflow_templates._common import _add_query_block_gates

    wf: dict[str, Any] = {
        "states": [
            _state("product_backlog", "Product Backlog", category="draft", badge="muted"),
            _state("planificado", "Planificada en sprint", category="draft", badge="muted"),
            _state("pendiente", "Pendiente", category="pending"),
            _state("en_progreso", "En progreso", category="active"),
            _state("completado", "Completado", category="terminal", badge="success", is_terminal=True),
            _state("cancelado", "Cancelado", category="terminal", badge="muted", is_terminal=True),
        ],
        "initial_state": "product_backlog",
        "terminal_states": ["completado", "cancelado"],
        "transitions": [
            {
                "id": "planificar_sprint",
                "label": "Planificar en sprint",
                "from": ["product_backlog"],
                "to": "planificado",
                "required_capabilities": [STORY_TRANSITION_COMPROMETER_SPRINT],
                "side_effects": [
                    {
                        "type": "reparent_to_sprint",
                        "value_from_context": "sprint_id",
                    },
                    {"type": "sync_scrum_sprint_dates"},
                ],
            },
            {
                "id": "publicar_sprint",
                "label": "Publicar en Sprint Board",
                "from": ["planificado"],
                "to": "pendiente",
                "required_capabilities": [STORY_TRANSITION_COMPROMETER_SPRINT],
            },
            {
                "id": "comprometer_sprint",
                "label": "Comprometer al Sprint",
                "from": ["product_backlog"],
                "to": "pendiente",
                "required_capabilities": [STORY_TRANSITION_COMPROMETER_SPRINT],
                "side_effects": [
                    {
                        "type": "reparent_to_sprint",
                        "value_from_context": "sprint_id",
                    },
                    {"type": "sync_scrum_sprint_dates"},
                ],
            },
            {
                "id": "volver_al_backlog",
                "label": "Volver al Product Backlog",
                "from": ["pendiente", "planificado"],
                "to": "product_backlog",
                "required_capabilities": [STORY_TRANSITION_VOLVER_BACKLOG],
                "side_effects": [{"type": "reparent_to_backlog"}],
            },
            {
                "id": "cancelar",
                "label": "Cancelar",
                "from": ["product_backlog", "planificado", "pendiente", "en_progreso"],
                "to": "cancelado",
                "required_capabilities": [STORY_TRANSITION_CANCELAR],
            },
            {
                "id": "completar",
                "label": "Completar",
                "from": ["en_progreso"],
                "to": "completado",
                "required_capabilities": [STORY_TRANSITION_COMPLETAR],
            },
        ],
    }
    wf["transitions"] = _add_query_block_gates(wf["transitions"])
    return wf


def default_task_workflow_scrum_story_interno() -> dict[str, Any]:
    return copy.deepcopy(default_task_workflow_scrum_story_base())


def default_task_workflow_scrum_story_cliente() -> dict[str, Any]:
    return copy.deepcopy(default_task_workflow_scrum_story_base())


def default_task_workflow_epic_container() -> dict[str, Any]:
    return {
        "states": [
            _state("abierta", "Abierta", category="active"),
            _state("cerrada", "Cerrada", category="terminal", badge="success", is_terminal=True),
        ],
        "initial_state": "abierta",
        "terminal_states": ["cerrada"],
        "transitions": [
            {
                "id": "move",
                "label": "Mover",
                "from": ["abierta", "cerrada"],
                "to": "*",
                "dynamic_to": True,
                "required_capabilities": [KANBAN_TASK_MOVE],
            },
            {
                "id": "cerrar",
                "label": "Cerrar épica",
                "from": ["abierta"],
                "to": "cerrada",
                "required_capabilities": [KANBAN_TASK_MOVE],
            },
        ],
    }


def default_task_workflow_scrum_dev() -> dict[str, Any]:
    """Workflow de tareas dev en Scrum (independiente del kanban waterfall)."""
    return {
        "states": [
            _state("backlog", "Backlog", category="backlog"),
            _state("to_do", "Por hacer", category="todo"),
            _state("in_progress", "En progreso", category="active"),
            _state("ready_for_test", "Listo para test", category="test"),
            _state("completed", "Completado", category="done", badge="success", is_terminal=True),
            _state("cancel", "Cancelado", category="terminal", badge="muted", is_terminal=True),
        ],
        "initial_state": "to_do",
        "terminal_states": ["completed", "cancel"],
        "transitions": [
            {
                "id": "move",
                "label": "Mover",
                "from": [
                    "backlog",
                    "to_do",
                    "in_progress",
                    "ready_for_test",
                    "completed",
                    "cancel",
                ],
                "to": "*",
                "required_capabilities": [KANBAN_TASK_MOVE],
                "dynamic_to": True,
            },
            {
                "id": "cancel",
                "label": "Cancelar",
                "from": ["backlog", "to_do", "in_progress", "ready_for_test"],
                "to": "cancel",
                "required_capabilities": [KANBAN_TASK_CANCEL],
            },
            {
                "id": "completar",
                "label": "Completar",
                "from": ["in_progress", "ready_for_test"],
                "to": "completed",
                "required_capabilities": [KANBAN_TASK_MOVE],
            },
        ],
    }


def default_sprint_workflow() -> dict[str, Any]:
    """Workflow de sprint Scrum (independiente del milestone waterfall)."""
    return {
        "states": [
            _state("pendiente", "Pendiente", category="pending"),
            _state("en_progreso", "En progreso", category="active"),
            _state("completado", "Completado", category="terminal", badge="success", is_terminal=True),
            _state("cancelado", "Cancelado", category="terminal", badge="muted", is_terminal=True),
        ],
        "initial_state": "pendiente",
        "terminal_states": ["completado", "cancelado"],
        "transitions": [
            {
                "id": "cancelar",
                "label": "Cancelar sprint",
                "from": ["pendiente", "en_progreso", "completado"],
                "to": "cancelado",
                "required_capabilities": [SCOPE_SPRINT_CANCEL],
                "side_effects": [{"type": "cancel_stories_cascade"}],
            },
            {
                "id": "sync",
                "label": "Sync automático",
                "from": ["*"],
                "to": "*",
                "required_capabilities": [],
                "dynamic_to": True,
            },
        ],
    }


def default_product_backlog_workflow() -> dict[str, Any]:
    """Contenedor raíz del Product Backlog (Scrum)."""
    return {
        "states": [
            _state("activo", "Activo", category="active"),
        ],
        "initial_state": "activo",
        "terminal_states": [],
        "transitions": [
            {
                "id": "sync",
                "label": "Sync automático",
                "from": ["*"],
                "to": "*",
                "required_capabilities": [],
                "dynamic_to": True,
            },
        ],
    }
