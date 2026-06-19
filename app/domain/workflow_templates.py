"""
Plantillas de workflow por defecto (equivalentes al comportamiento legacy).
"""
from __future__ import annotations

import copy
from typing import Any

from app.domain.capabilities import (
    KANBAN_TASK_CANCEL,
    SCOPE_MILESTONE_CANCEL,
    SCOPE_SPRINT_CANCEL,
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
    KANBAN_TASK_MOVE,
)

EntityType = str  # feature | task | query | report | milestone

_COND_HAS_CLIENTE: dict[str, Any] = {"type": "has_role", "slug": "cliente"}
_COND_NO_CLIENTE: dict[str, Any] = {"type": "has_role", "slug": "cliente", "negate": True}
_COND_PROJECT_TIPO_FREESTYLE: dict[str, Any] = {"type": "project_tipo", "in": ["freestyle"]}

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
                "Espera PM",
                category="inbox_pm",
            ),
            _state(
                "esperando_validacion_cliente",
                "Espera cliente",
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
                    {"type": "notify", "target": {"capability": "workbench.scope"}},
                ],
            },
            {
                "id": "liberar_cliente",
                "label": "Liberar al cliente",
                "from": ["esperando_liberacion_pm"],
                "to": "esperando_validacion_cliente",
                "required_capabilities": [FEATURE_TRANSITION_LIBERAR_CLIENTE],
                "conditions": [_COND_HAS_CLIENTE],
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
                "conditions": [_COND_HAS_CLIENTE],
            },
            {
                "id": "no_funciona",
                "label": "No funciona",
                "from": ["esperando_validacion_cliente"],
                "to": "en_progreso",
                "required_capabilities": [FEATURE_TRANSITION_NO_FUNCIONA],
                "conditions": [_COND_HAS_CLIENTE],
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
            "conditions": [_COND_NO_CLIENTE],
            "gates": [_QUERY_BLOCK_GATE],
        }
    )
    return wf


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
    """Historia Scrum como task: workflow ex-feature con reparent al sprint."""
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
            "required_capabilities": [STORY_TRANSITION_COMPROMETER_SPRINT],
            "side_effects": [
                {
                    "type": "reparent_to_sprint",
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
            "required_capabilities": [STORY_TRANSITION_VOLVER_BACKLOG],
            "side_effects": [{"type": "reparent_to_backlog"}],
        },
    ]
    wf["transitions"] = transitions
    return _map_feature_caps_to_story(wf)


def default_task_workflow_scrum_story_interno() -> dict[str, Any]:
    wf = default_task_workflow_scrum_story_base()
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
            "required_capabilities": [STORY_TRANSITION_COMPLETAR],
            "conditions": [_COND_NO_CLIENTE],
            "gates": [_QUERY_BLOCK_GATE],
        }
    )
    return wf


def default_task_workflow_scrum_story_cliente() -> dict[str, Any]:
    return default_task_workflow_scrum_story_base()


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
                "id": "cerrar",
                "label": "Cerrar épica",
                "from": ["abierta"],
                "to": "cerrada",
                "required_capabilities": [KANBAN_TASK_MOVE],
            },
        ],
    }


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
                "id": "completar",
                "label": "Completar",
                "from": ["backlog", "to_do", "in_progress", "ready_for_test"],
                "to": "completed",
                "required_capabilities": [STORY_TRANSITION_COMPLETAR, KANBAN_TASK_MOVE],
            },
            {
                "id": "reabrir",
                "label": "Reabrir",
                "from": ["completed"],
                "to": "to_do",
                "required_capabilities": [STORY_TRANSITION_COMPLETAR, KANBAN_TASK_MOVE],
            },
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
            _state("esperando_pm", "Esperando PM", category="inbox_pm"),
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
                "conditions": [_COND_HAS_CLIENTE],
            },
            {
                "id": "solicitar_envio",
                "label": "Solicitar envío",
                "from": ["borrador"],
                "to": "esperando_pm",
                "required_capabilities": ["query.send"],
                "conditions": [_COND_NO_CLIENTE],
            },
            {
                "id": "aprobar_envio",
                "label": "Aprobar envío",
                "from": ["pendiente_aprobacion_pm"],
                "to": "esperando_cliente",
                "required_capabilities": ["query.approve"],
                "conditions": [_COND_HAS_CLIENTE],
            },
            {
                "id": "activar",
                "label": "Activar",
                "from": ["borrador"],
                "to": "esperando_cliente",
                "required_capabilities": ["query.send"],
                "conditions": [_COND_HAS_CLIENTE],
            },
            {
                "id": "activar",
                "label": "Activar",
                "from": ["borrador"],
                "to": "esperando_pm",
                "required_capabilities": ["query.send"],
                "conditions": [_COND_NO_CLIENTE],
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
                "conditions": [_COND_NO_CLIENTE],
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
            _state("pendiente", "Pendiente", category="inbox_shared"),
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
                "conditions": [_COND_HAS_CLIENTE],
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
                "conditions": [_COND_HAS_CLIENTE],
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
    wf = copy.deepcopy(default_feature_workflow_con_cliente())
    transitions = list(wf["transitions"])
    transitions.append(
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
    transitions.append(
        {
            "id": "completar",
            "label": "Completar (sin cliente)",
            "from": ["esperando_liberacion_pm"],
            "to": "completado",
            "required_capabilities": [FEATURE_TRANSITION_COMPLETAR],
            "conditions": [_COND_PROJECT_TIPO_FREESTYLE],
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
            "conditions": [_COND_PROJECT_TIPO_FREESTYLE],
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
            "conditions": [_COND_PROJECT_TIPO_FREESTYLE],
        },
        {
            "id": "activar_cliente",
            "label": "Activar (cliente)",
            "from": ["borrador"],
            "to": "esperando_cliente",
            "required_capabilities": ["query.send"],
            "conditions": [_COND_PROJECT_TIPO_FREESTYLE],
        },
        {
            "id": "activar_interno",
            "label": "Activar (interno)",
            "from": ["borrador"],
            "to": "esperando_pm",
            "required_capabilities": ["query.send"],
            "conditions": [_COND_PROJECT_TIPO_FREESTYLE],
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
            "conditions": [_COND_PROJECT_TIPO_FREESTYLE],
            "gates": [{"type": "project_active"}],
            "side_effects": [
                {"type": "notify_reporter", "notification_tipo": "reporte_resuelto"},
            ],
        },
    ]
    return wf


_TEMPLATE_TO_TIPO: dict[str, str] = {
    "t1_cliente_clasico": "con_cliente",
    "t2_cliente_pm_tecnico": "con_cliente",
    "t3_interno_clasico": "interno",
    "t4_interno_pm_tecnico": "interno",
    "t5_freestyle": "freestyle",
}


def workflow_for_template(template_slug: str, entity_type: str) -> dict[str, Any]:
    """Resuelve el workflow por template_slug."""
    from app.domain.project_templates import SCRUM_TEMPLATE_SLUGS

    if entity_type == "feature":
        if template_slug == "t6_scrum_interno":
            return default_feature_workflow_scrum_interno()
        if template_slug == "t7_scrum_cliente":
            return default_feature_workflow_scrum_cliente()
    if entity_type == "sprint" and template_slug in SCRUM_TEMPLATE_SLUGS:
        return default_sprint_workflow()
    if entity_type == "product_backlog" and template_slug in SCRUM_TEMPLATE_SLUGS:
        return default_product_backlog_workflow()
    tipo = _TEMPLATE_TO_TIPO.get(template_slug, "interno")
    return workflow_for_project_tipo(tipo, entity_type)


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
