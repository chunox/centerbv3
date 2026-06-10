"""
Plantillas de workflow por defecto (equivalentes al comportamiento legacy).
"""
from __future__ import annotations

import copy
from typing import Any

from app.domain.capabilities import (
    KANBAN_TASK_CANCEL,
    SCOPE_MILESTONE_CANCEL,
    FEATURE_TRANSITION_CANCELAR,
    FEATURE_TRANSITION_COMPLETAR,
    FEATURE_TRANSITION_CONFIRMAR,
    FEATURE_TRANSITION_DEVOLVER_REWORK,
    FEATURE_TRANSITION_ENVIAR_AL_PM,
    FEATURE_TRANSITION_LIBERAR_CLIENTE,
    FEATURE_TRANSITION_NO_FUNCIONA,
    FEATURE_TRANSITION_PASAR_A_UAT,
    FEATURE_TRANSITION_RECHAZAR_LIBERACION,
    KANBAN_TASK_MOVE,
)

EntityType = str  # feature | task | query | report | milestone

_QUERY_BLOCK_GATE: dict[str, Any] = {"type": "blocked_by_active_query"}
_TRANSITIONS_NEEDING_QUERY_GATE = frozenset(
    {
        "pasar_a_uat",
        "enviar_al_pm",
        "devolver_rework",
        "liberar_cliente",
        "rechazar_liberacion",
        "confirmar",
        "no_funciona",
        "completar",
    }
)


def _add_query_block_gates(transitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in transitions:
        if t.get("id") in _TRANSITIONS_NEEDING_QUERY_GATE:
            gates = list(t.get("gates", []))
            if _QUERY_BLOCK_GATE not in gates:
                gates.append(_QUERY_BLOCK_GATE)
            t = {**t, "gates": gates}
        out.append(t)
    return out


def _state(
    key: str,
    label: str,
    *,
    category: str = "active",
    badge: str = "info",
    is_terminal: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "category": category,
        "badge": badge,
        "is_terminal": is_terminal,
    }


def default_feature_workflow_con_cliente() -> dict[str, Any]:
    wf = {
        "states": [
            _state("pendiente", "Pendiente", category="pending"),
            _state("en_progreso", "En progreso", category="active"),
            _state("uat", "UAT", category="uat"),
            _state(
                "esperando_liberacion_pm",
                "Esperando liberación PM",
                category="inbox_pm",
            ),
            _state(
                "esperando_validacion_cliente",
                "Esperando validación cliente",
                category="inbox_client",
            ),
            _state("completado", "Completado", category="terminal", badge="success", is_terminal=True),
            _state("cancelado", "Cancelado", category="terminal", badge="muted", is_terminal=True),
        ],
        "initial_state": "pendiente",
        "terminal_states": ["completado", "cancelado"],
        "transitions": [
            {
                "id": "pasar_a_uat",
                "label": "Pasar a UAT",
                "from": ["en_progreso"],
                "to": "uat",
                "required_capabilities": [FEATURE_TRANSITION_PASAR_A_UAT],
                "gates": [{"type": "uat_tasks_complete"}],
                "side_effects": [
                    {"type": "notify", "target": {"capability": "workbench.uat"}}
                ],
            },
            {
                "id": "cancelar",
                "label": "Cancelar",
                "from": ["pendiente", "en_progreso", "uat", "esperando_liberacion_pm", "esperando_validacion_cliente"],
                "to": "cancelado",
                "required_capabilities": [FEATURE_TRANSITION_CANCELAR],
                "side_effects": [{"type": "cancel_tasks_cascade"}],
            },
            {
                "id": "enviar_al_pm",
                "label": "Enviar al PM",
                "from": ["uat"],
                "to": "esperando_liberacion_pm",
                "required_capabilities": [FEATURE_TRANSITION_ENVIAR_AL_PM],
                "side_effects": [
                    {"type": "sync_tasks", "rule": "complete_ready_for_test"},
                    {"type": "notify", "target": {"capability": "workbench.inbox.pm"}},
                ],
            },
            {
                "id": "devolver_rework",
                "label": "Devolver rework",
                "from": ["uat"],
                "to": "en_progreso",
                "required_capabilities": [FEATURE_TRANSITION_DEVOLVER_REWORK],
                "side_effects": [
                    {"type": "rework_tasks"},
                    {"type": "notify", "target": {"capability": "workbench.my_deliveries"}},
                ],
            },
            {
                "id": "liberar_cliente",
                "label": "Liberar al cliente",
                "from": ["esperando_liberacion_pm"],
                "to": "esperando_validacion_cliente",
                "required_capabilities": [FEATURE_TRANSITION_LIBERAR_CLIENTE],
                "conditions": [{"type": "project_tipo", "in": ["con_cliente"]}],
                "side_effects": [
                    {"type": "notify", "target": {"capability": "workbench.inbox.client"}}
                ],
            },
            {
                "id": "rechazar_liberacion",
                "label": "Rechazar liberación",
                "from": ["esperando_liberacion_pm"],
                "to": "en_progreso",
                "required_capabilities": [FEATURE_TRANSITION_RECHAZAR_LIBERACION],
                "side_effects": [{"type": "rework_tasks"}],
            },
            {
                "id": "confirmar",
                "label": "Confirmar",
                "from": ["esperando_validacion_cliente"],
                "to": "completado",
                "required_capabilities": [FEATURE_TRANSITION_CONFIRMAR],
                "conditions": [{"type": "project_tipo", "in": ["con_cliente"]}],
            },
            {
                "id": "no_funciona",
                "label": "No funciona",
                "from": ["esperando_validacion_cliente"],
                "to": "en_progreso",
                "required_capabilities": [FEATURE_TRANSITION_NO_FUNCIONA],
                "conditions": [{"type": "project_tipo", "in": ["con_cliente"]}],
                "side_effects": [{"type": "rework_tasks"}],
            },
        ],
    }
    wf["transitions"] = _add_query_block_gates(wf["transitions"])
    return wf


def default_feature_workflow_interno() -> dict[str, Any]:
    wf = default_feature_workflow_con_cliente()
    wf["transitions"] = [
        t
        for t in wf["transitions"]
        if t["id"]
        not in ("liberar_cliente", "confirmar", "no_funciona")
    ]
    wf["transitions"].append(
        {
            "id": "completar",
            "label": "Completar",
            "from": ["esperando_liberacion_pm"],
            "to": "completado",
            "required_capabilities": [FEATURE_TRANSITION_COMPLETAR],
            "conditions": [{"type": "project_tipo", "in": ["interno"]}],
            "gates": [_QUERY_BLOCK_GATE],
        }
    )
    return wf


def default_task_workflow() -> dict[str, Any]:
    return {
        "states": [
            _state("backlog", "Backlog", category="backlog"),
            _state("to_do", "Por hacer", category="todo"),
            _state("in_progress", "En progreso", category="active"),
            _state("ready_for_test", "Listo para test", category="test"),
            _state("completed", "Completado", category="done", badge="success", is_terminal=True),
            _state("cancel", "Cancelado", category="terminal", badge="muted", is_terminal=True),
        ],
        "initial_state": "backlog",
        "terminal_states": ["completed", "cancel"],
        "transitions": [
            {
                "id": "move",
                "label": "Mover",
                "from": ["backlog", "to_do", "in_progress", "ready_for_test"],
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
        ],
    }


def default_query_workflow() -> dict[str, Any]:
    return {
        "states": [
            _state("borrador", "Borrador", category="draft"),
            _state("pendiente_aprobacion_pm", "Pendiente aprobación PM", category="inbox_pm"),
            _state("esperando_cliente", "Esperando cliente", category="inbox_client"),
            _state("esperando_pm", "Esperando PM", category="active"),
            _state("respuesta_cliente", "Respuesta cliente", category="inbox_pm"),
            _state("cerrada", "Cerrada", category="terminal", is_terminal=True),
            _state("rechazada", "Rechazada", category="terminal", is_terminal=True),
        ],
        "initial_state": "borrador",
        "terminal_states": ["cerrada", "rechazada"],
        "transitions": [
            {
                "id": "solicitar_envio",
                "label": "Solicitar envío",
                "from": ["borrador"],
                "to": "pendiente_aprobacion_pm",
                "required_capabilities": ["query.send"],
                "conditions": [{"type": "project_tipo", "in": ["con_cliente"]}],
            },
            {
                "id": "solicitar_envio",
                "label": "Solicitar envío",
                "from": ["borrador"],
                "to": "esperando_pm",
                "required_capabilities": ["query.send"],
                "conditions": [{"type": "project_tipo", "in": ["interno"]}],
            },
            {
                "id": "aprobar_envio",
                "label": "Aprobar envío",
                "from": ["pendiente_aprobacion_pm"],
                "to": "esperando_cliente",
                "required_capabilities": ["query.approve"],
                "conditions": [{"type": "project_tipo", "in": ["con_cliente"]}],
            },
            {
                "id": "activar",
                "label": "Activar",
                "from": ["borrador"],
                "to": "esperando_cliente",
                "required_capabilities": ["query.send"],
                "conditions": [{"type": "project_tipo", "in": ["con_cliente"]}],
            },
            {
                "id": "activar",
                "label": "Activar",
                "from": ["borrador"],
                "to": "esperando_pm",
                "required_capabilities": ["query.send"],
                "conditions": [{"type": "project_tipo", "in": ["interno"]}],
            },
            {
                "id": "responder",
                "label": "Responder",
                "from": ["esperando_cliente"],
                "to": "respuesta_cliente",
                "required_capabilities": ["query.respond"],
            },
            {
                "id": "validar_aceptar",
                "label": "Validar respuesta",
                "from": ["respuesta_cliente"],
                "to": "cerrada",
                "required_capabilities": ["query.close"],
            },
            {
                "id": "validar_rechazar",
                "label": "Pedir nueva respuesta",
                "from": ["respuesta_cliente"],
                "to": "esperando_cliente",
                "required_capabilities": ["query.close"],
            },
            {
                "id": "cerrar",
                "label": "Cerrar",
                "from": ["esperando_pm"],
                "to": "cerrada",
                "required_capabilities": ["query.close"],
                "conditions": [{"type": "project_tipo", "in": ["interno"]}],
            },
            {
                "id": "rechazar",
                "label": "Rechazar",
                "from": [
                    "pendiente_aprobacion_pm",
                    "esperando_cliente",
                    "esperando_pm",
                    "respuesta_cliente",
                ],
                "to": "rechazada",
                "required_capabilities": ["query.close"],
            },
        ],
    }


def default_report_workflow() -> dict[str, Any]:
    return {
        "states": [
            _state("pendiente", "Pendiente", category="inbox_pm"),
            _state("aprobado", "Aprobado", category="terminal", badge="success", is_terminal=True),
            _state("rechazado", "Rechazado", category="terminal", badge="muted", is_terminal=True),
        ],
        "initial_state": "pendiente",
        "terminal_states": ["aprobado", "rechazado"],
        "transitions": [
            {
                "id": "aprobar",
                "label": "Aprobar",
                "from": ["pendiente"],
                "to": "aprobado",
                "required_capabilities": ["report.approve"],
                "conditions": [{"type": "project_tipo", "in": ["con_cliente"]}],
                "gates": [
                    {"type": "project_active"},
                    {"type": "report_source_feature_complete"},
                ],
                "form_fields": [
                    {
                        "id": "nombre_feature",
                        "label": "Nombre de la feature generada",
                        "type": "text",
                        "required": False,
                    },
                    {
                        "id": "duracion_estimada",
                        "label": "Duración estimada (días)",
                        "type": "number",
                        "required": False,
                    },
                ],
                "side_effects": [
                    {"type": "generate_feature_from_report"},
                    {"type": "notify_reporter", "notification_tipo": "reporte_resuelto"},
                    {"type": "sync_milestone_from_report"},
                ],
            },
            {
                "id": "rechazar",
                "label": "Rechazar",
                "from": ["pendiente"],
                "to": "rechazado",
                "required_capabilities": ["report.reject"],
                "conditions": [{"type": "project_tipo", "in": ["con_cliente"]}],
                "gates": [{"type": "project_active"}],
                "side_effects": [
                    {"type": "notify_reporter", "notification_tipo": "reporte_resuelto"},
                ],
            },
        ],
    }


def default_milestone_workflow() -> dict[str, Any]:
    return {
        "states": [
            _state("pendiente", "Pendiente", category="pending"),
            _state("en_progreso", "En progreso", category="active"),
            _state("completado", "Completado", category="terminal", badge="success", is_terminal=True),
            _state("en_progreso_con_bug", "En progreso con bug", category="active", badge="warning"),
            _state("cerrado_con_bug", "Cerrado con bug", category="terminal", badge="warning", is_terminal=True),
            _state("cancelado", "Cancelado", category="terminal", badge="muted", is_terminal=True),
        ],
        "initial_state": "pendiente",
        "terminal_states": ["completado", "cerrado_con_bug", "cancelado"],
        "transitions": [
            {
                "id": "cancelar",
                "label": "Cancelar hito",
                "from": ["pendiente", "en_progreso", "en_progreso_con_bug", "completado", "cerrado_con_bug"],
                "to": "cancelado",
                "required_capabilities": [SCOPE_MILESTONE_CANCEL],
                "side_effects": [{"type": "cancel_features_cascade"}],
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


def _expand_project_tipo_in_workflow(
    wf: dict[str, Any], extra_tipo: str
) -> dict[str, Any]:
    """Añade extra_tipo a condiciones project_tipo existentes."""
    out = copy.deepcopy(wf)
    for transition in out.get("transitions", []):
        for cond in transition.get("conditions", []):
            if cond.get("type") == "project_tipo":
                allowed = list(cond.get("in", []))
                if extra_tipo not in allowed:
                    allowed.append(extra_tipo)
                cond["in"] = allowed
    return out


def _unify_project_tipo_conditions(wf: dict[str, Any]) -> dict[str, Any]:
    """Freestyle: todas las ramas por tipo quedan disponibles según capacidades."""
    out = copy.deepcopy(wf)
    all_tipos = ["con_cliente", "interno", "freestyle"]
    for transition in out.get("transitions", []):
        for cond in transition.get("conditions", []):
            if cond.get("type") == "project_tipo":
                cond["in"] = all_tipos
    return out


def default_feature_workflow_freestyle() -> dict[str, Any]:
    wf = _unify_project_tipo_conditions(default_feature_workflow_con_cliente())
    transitions = list(wf["transitions"])
    transitions.append(
        {
            "id": "completar",
            "label": "Completar (sin cliente)",
            "from": ["esperando_liberacion_pm"],
            "to": "completado",
            "required_capabilities": [FEATURE_TRANSITION_COMPLETAR],
            "conditions": [{"type": "project_tipo", "in": ["freestyle"]}],
            "gates": [_QUERY_BLOCK_GATE],
        }
    )
    transitions.append(
        {
            "id": "completar_directo_uat",
            "label": "Completar desde UAT",
            "from": ["uat"],
            "to": "completado",
            "required_capabilities": [FEATURE_TRANSITION_COMPLETAR],
            "conditions": [{"type": "project_tipo", "in": ["freestyle"]}],
            "gates": [
                _QUERY_BLOCK_GATE,
                {"type": "uat_tasks_complete"},
            ],
        }
    )
    wf["transitions"] = _add_query_block_gates(transitions)
    return wf


def default_query_workflow_freestyle() -> dict[str, Any]:
    wf = _expand_project_tipo_in_workflow(default_query_workflow(), "freestyle")
    wf["transitions"] = list(wf["transitions"]) + [
        {
            "id": "cerrar_directo",
            "label": "Cerrar sin cliente",
            "from": ["borrador", "pendiente_aprobacion_pm", "esperando_pm"],
            "to": "cerrada",
            "required_capabilities": ["query.close"],
            "conditions": [{"type": "project_tipo", "in": ["freestyle"]}],
        },
        {
            "id": "activar_cliente",
            "label": "Activar (cliente)",
            "from": ["borrador"],
            "to": "esperando_cliente",
            "required_capabilities": ["query.send"],
            "conditions": [{"type": "project_tipo", "in": ["freestyle"]}],
        },
        {
            "id": "activar_interno",
            "label": "Activar (interno)",
            "from": ["borrador"],
            "to": "esperando_pm",
            "required_capabilities": ["query.send"],
            "conditions": [{"type": "project_tipo", "in": ["freestyle"]}],
        },
    ]
    return wf


def default_report_workflow_freestyle() -> dict[str, Any]:
    wf = _expand_project_tipo_in_workflow(default_report_workflow(), "freestyle")
    wf["transitions"] = list(wf["transitions"]) + [
        {
            "id": "aprobar_sin_feature",
            "label": "Aprobar sin generar feature",
            "from": ["pendiente"],
            "to": "aprobado",
            "required_capabilities": ["report.approve"],
            "conditions": [{"type": "project_tipo", "in": ["freestyle"]}],
            "gates": [{"type": "project_active"}],
            "side_effects": [
                {"type": "notify_reporter", "notification_tipo": "reporte_resuelto"},
            ],
        },
    ]
    return wf


def workflow_for_project_tipo(tipo: str, entity_type: str) -> dict[str, Any]:
    if tipo == "freestyle":
        if entity_type == "feature":
            return default_feature_workflow_freestyle()
        if entity_type == "query":
            return default_query_workflow_freestyle()
        if entity_type == "report":
            return default_report_workflow_freestyle()
        if entity_type == "task":
            return default_task_workflow()
        if entity_type == "milestone":
            return default_milestone_workflow()
        raise ValueError(f"entity_type desconocido: {entity_type}")

    if entity_type == "feature":
        return (
            default_feature_workflow_con_cliente()
            if tipo == "con_cliente"
            else default_feature_workflow_interno()
        )
    if entity_type == "task":
        return default_task_workflow()
    if entity_type == "query":
        return default_query_workflow()
    if entity_type == "report":
        return default_report_workflow()
    if entity_type == "milestone":
        return default_milestone_workflow()
    raise ValueError(f"entity_type desconocido: {entity_type}")
