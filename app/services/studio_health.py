"""Health check de configuración Studio."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import Project
from app.services.communication.store import get_communication_rules
from app.services.workflow.store import get_active_workflow, get_workbenches


def build_studio_health(db: Session, project: Project) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    workbenches = get_workbenches(db, project.id)
    all_categories: set[str] = set()
    all_actions: set[str] = set()
    all_states: set[str] = set()

    record_types = {rt.key for rt in project.record_types} if hasattr(project, "record_types") else set()
    from app.services.packs import list_record_types

    record_types = {rt.key for rt in list_record_types(db, project.id)}

    for rt_key in record_types:
        wf = get_active_workflow(db, project.id, rt_key)
        if not wf:
            continue
        for state in wf.get("states") or []:
            if isinstance(state, dict) and state.get("key"):
                all_states.add(str(state["key"]))
                cat = state.get("category")
                if cat:
                    all_categories.add(str(cat))
        for transition in wf.get("transitions") or []:
            if transition.get("id"):
                all_actions.add(str(transition["id"]))
            allowed = transition.get("allowed_role_slugs") or []
            if "allowed_role_slugs" in transition and not allowed:
                issues.append(
                    {
                        "code": "transition_no_roles",
                        "message": f"Transición '{transition.get('id')}' en {rt_key} sin roles",
                        "entity_type": rt_key,
                    }
                )

    for wb in workbenches:
        qf = wb.get("queue_filter") or {}
        for cat in qf.get("state_categories") or []:
            if cat not in all_categories and cat not in {
                "inbox_shared",
                "backlog",
                "todo",
                "test",
                "done",
                "terminal",
                "uat",
                "draft",
            }:
                issues.append(
                    {
                        "code": "unknown_category",
                        "message": f"Workbench '{wb.get('key')}' referencia categoría '{cat}' inexistente",
                        "workbench_key": str(wb.get("key")),
                    }
                )

    for rule in get_communication_rules(db, project.id):
        match = rule.match
        if match.action_id and match.action_id not in all_actions:
            issues.append(
                {
                    "code": "orphan_action",
                    "message": f"Regla '{rule.id}' referencia action '{match.action_id}'",
                    "rule_id": rule.id,
                }
            )
        if match.to_state and match.to_state not in all_states and match.to_state not in {
            "bloqueada",
            "desbloqueada",
        }:
            issues.append(
                {
                    "code": "orphan_state",
                    "message": f"Regla '{rule.id}' referencia estado '{match.to_state}'",
                    "rule_id": rule.id,
                }
            )

    return {"issues": issues, "issue_count": len(issues)}
