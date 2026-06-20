"""Helpers compartidos para plantillas de workflow."""
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

