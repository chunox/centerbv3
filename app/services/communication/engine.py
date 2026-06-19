"""Motor de reglas de comunicación entre actores."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.domain.capabilities import WORKBENCH_INBOX_CLIENT, WORKBENCH_INBOX_PM
from app.models.entities import Project, ProjectRecord
from app.services.communication.store import get_communication_rules
from app.services.notifications import NotificationTipo, create_notification
from app.services.project_profile import supports_external_stakeholder
from app.services.records.registry import registry
from app.services.workflow.capabilities import user_ids_with_role_slug, users_with_capability


@dataclass
class CommunicationContext:
    event: str
    project: Project
    author_id: uuid.UUID
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    action_id: str | None = None
    from_state: str | None = None
    to_state: str | None = None
    comment_entity_type: str | None = None
    record_type: str | None = None
    record: ProjectRecord | None = None
    mentioned_ids: set[uuid.UUID] | None = None
    sandbox: bool = False


@dataclass
class CommunicationDispatchResult:
    rule_id: str
    recipient_ids: list[uuid.UUID] = field(default_factory=list)
    notification_tipo: str = "estado_changed"
    deep_link: dict[str, Any] = field(default_factory=dict)


CLIENT_QUERY_STATES = frozenset({"esperando_cliente", "respuesta_cliente"})


def _record_data(record: ProjectRecord) -> dict[str, Any]:
    raw = record.data
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _notification_entidad_tipo(ctx: CommunicationContext) -> str:
    if ctx.comment_entity_type:
        return ctx.comment_entity_type
    if ctx.entity_type:
        return registry.audit_entidad_tipo(ctx.entity_type)
    if ctx.record_type:
        return registry.audit_entidad_tipo(ctx.record_type)
    return "feature"


def _rule_matches(rule: dict[str, Any], ctx: CommunicationContext) -> bool:
    if not rule.get("enabled", True):
        return False
    if rule.get("event") != ctx.event:
        return False
    match = rule.get("match") or {}
    if ctx.entity_type and match.get("entity_type") not in (None, ctx.entity_type):
        return False
    record_type = ctx.record_type or (ctx.record.record_type if ctx.record else None)
    if record_type and match.get("record_type") not in (None, record_type):
        return False
    if ctx.action_id and match.get("action_id") not in (None, ctx.action_id):
        return False
    if ctx.to_state and match.get("to_state") not in (None, ctx.to_state):
        return False
    if ctx.from_state and match.get("from_state") not in (None, ctx.from_state):
        return False
    if ctx.comment_entity_type and match.get("comment_entity_type") not in (
        None,
        ctx.comment_entity_type,
    ):
        return False
    expected_scrum_role = match.get("scrum_role")
    if expected_scrum_role is not None:
        record = ctx.record
        if record is None:
            return False
        data = record.data if isinstance(record.data, dict) else {}
        if data.get("scrum_role") != expected_scrum_role:
            return False
    return True


def _resolve_recipients(
    db: Session,
    ctx: CommunicationContext,
    recipient: dict[str, Any],
    delivery: dict[str, Any],
) -> set[uuid.UUID]:
    rtype = recipient.get("type")
    value = recipient.get("value")
    out: set[uuid.UUID] = set()
    record = ctx.record

    if rtype == "capability" and value:
        out.update(users_with_capability(db, ctx.project.id, value))
    elif rtype == "role" and value:
        out.update(user_ids_with_role_slug(db, ctx.project.id, value))
    elif rtype == "author" and record is not None and record.created_by:
        out.add(record.created_by)
    elif rtype == "record_field" and record is not None and value:
        data = _record_data(record)
        field_val = data.get(value) or getattr(record, value, None)
        if field_val:
            try:
                out.add(uuid.UUID(str(field_val)))
            except (ValueError, TypeError):
                pass
        elif record.created_by:
            out.add(record.created_by)
    elif rtype == "thread_participants":
        if ctx.entity_id and ctx.comment_entity_type:
            from sqlalchemy import select

            from app.models.entities import Comment as CommentModel

            rows = db.scalars(
                select(CommentModel.user_id).where(
                    CommentModel.entidad_tipo == ctx.comment_entity_type,
                    CommentModel.entidad_id == ctx.entity_id,
                )
            )
            out.update(rows)

    match_states = delivery.get("match_states")
    if match_states and record is not None:
        if record.estado not in frozenset(match_states):
            return set()

    if (
        rtype == "capability"
        and value == WORKBENCH_INBOX_CLIENT
        and record is not None
        and record.record_type == "query"
    ):
        if not supports_external_stakeholder(db, ctx.project):
            return set()
        if record.estado not in CLIENT_QUERY_STATES:
            return set()

    out.discard(ctx.author_id)
    if ctx.mentioned_ids:
        out -= ctx.mentioned_ids
    return out


def _build_deep_link(
    delivery: dict[str, Any],
    ctx: CommunicationContext,
) -> dict[str, Any] | None:
    raw = delivery.get("deep_link") or {}
    if not raw:
        return None
    link = dict(raw)
    if ctx.entity_id and "record_id" not in link:
        link["record_id"] = str(ctx.entity_id)
    return link


def _resolve_message_template(template: str, ctx: CommunicationContext) -> str:
    record = ctx.record
    replacements = {
        "{entity_type}": ctx.entity_type or "",
        "{to_state}": ctx.to_state or "",
        "{from_state}": ctx.from_state or "",
    }
    if record is not None:
        replacements["{title}"] = record.titulo or ""
        replacements["{estado}"] = record.estado or ""
    out = template
    for key, value in replacements.items():
        out = out.replace(key, value)
    return out


def simulate_communication_rules(
    db: Session,
    ctx: CommunicationContext,
) -> list[CommunicationDispatchResult]:
    rules = get_communication_rules(db, ctx.project.id)
    if ctx.entity_id is None:
        return []
    results: list[CommunicationDispatchResult] = []
    for rule in rules:
        rule_dict = rule.model_dump()
        if not _rule_matches(rule_dict, ctx):
            continue
        for delivery in rule_dict.get("deliveries") or []:
            recipients = delivery.get("recipients") or {}
            notif = delivery.get("notification") or {}
            tipo = str(notif.get("tipo", "estado_changed"))
            recipient_ids = sorted(
                _resolve_recipients(db, ctx, recipients, delivery),
                key=str,
            )
            results.append(
                CommunicationDispatchResult(
                    rule_id=str(rule_dict.get("id", "")),
                    recipient_ids=recipient_ids,
                    notification_tipo=tipo,
                    deep_link=_build_deep_link(delivery, ctx) or {},
                )
            )
    return results


def dispatch_communication_rules(
    db: Session,
    ctx: CommunicationContext,
) -> list[CommunicationDispatchResult]:
    rules = get_communication_rules(db, ctx.project.id)
    if ctx.entity_id is None:
        return []

    entidad_tipo = _notification_entidad_tipo(ctx)
    entidad_id = ctx.entity_id
    dispatched: list[CommunicationDispatchResult] = []

    for rule in rules:
        rule_dict = rule.model_dump()
        if not _rule_matches(rule_dict, ctx):
            continue
        for delivery in rule_dict.get("deliveries") or []:
            recipients = delivery.get("recipients") or {}
            notif = delivery.get("notification") or {}
            tipo = str(notif.get("tipo", "estado_changed"))
            deep_link = _build_deep_link(delivery, ctx)
            message_template = notif.get("message_template")
            recipient_ids: list[uuid.UUID] = []
            for uid in _resolve_recipients(db, ctx, recipients, delivery):
                if ctx.sandbox:
                    recipient_ids.append(uid)
                    continue
                create_notification(
                    db,
                    user_id=uid,
                    project_id=ctx.project.id,
                    tipo=tipo,  # type: ignore[arg-type]
                    entidad_tipo=entidad_tipo,  # type: ignore[arg-type]
                    entidad_id=entidad_id,
                    deep_link=deep_link,
                    message=(_resolve_message_template(message_template, ctx)
                             if message_template else None),
                )
                recipient_ids.append(uid)
            if recipient_ids:
                dispatched.append(
                    CommunicationDispatchResult(
                        rule_id=str(rule_dict.get("id", "")),
                        recipient_ids=recipient_ids,
                        notification_tipo=tipo,
                        deep_link=deep_link or {},
                    )
                )
                if not ctx.sandbox:
                    _log_dispatch(db, ctx, rule_dict, recipient_ids, tipo)
    return dispatched


def _log_dispatch(
    db: Session,
    ctx: CommunicationContext,
    rule: dict[str, Any],
    recipient_ids: list[uuid.UUID],
    tipo: str,
) -> None:
    from app.services.audit import record_audit_log

    if ctx.entity_id is None:
        return
    record_audit_log(
        db,
        project_id=ctx.project.id,
        user_id=ctx.author_id,
        entidad_tipo="communication_dispatch",
        entidad_id=ctx.entity_id,
        accion="created",
        campo=str(rule.get("id", "")),
        valor_nuevo=f"{tipo}:{len(recipient_ids)}",
    )


def dispatch_comment_rules(
    db: Session,
    *,
    project: Project,
    author_id: uuid.UUID,
    entidad_tipo: str,
    entidad_id: uuid.UUID,
    mentioned_ids: set[uuid.UUID],
) -> None:
    record = db.get(ProjectRecord, entidad_id)
    ctx = CommunicationContext(
        event="on_comment",
        project=project,
        author_id=author_id,
        comment_entity_type=entidad_tipo,
        entity_type=record.record_type if record else None,
        entity_id=entidad_id,
        record=record,
        mentioned_ids=mentioned_ids,
    )
    dispatch_communication_rules(db, ctx)


def dispatch_transition_rules(
    db: Session,
    *,
    project: Project,
    actor_user_id: uuid.UUID,
    record: ProjectRecord,
    action_id: str,
    from_state: str,
    to_state: str,
) -> None:
    ctx = CommunicationContext(
        event="on_transition",
        project=project,
        author_id=actor_user_id,
        entity_type=record.record_type,
        entity_id=record.id,
        action_id=action_id,
        from_state=from_state,
        to_state=to_state,
        record=record,
    )
    dispatch_communication_rules(db, ctx)


def dispatch_state_entered_rules(
    db: Session,
    *,
    project: Project,
    actor_user_id: uuid.UUID,
    record: ProjectRecord,
    to_state: str,
    from_state: str | None = None,
) -> None:
    ctx = CommunicationContext(
        event="on_state_entered",
        project=project,
        author_id=actor_user_id,
        entity_type=record.record_type,
        entity_id=record.id,
        to_state=to_state,
        from_state=from_state,
        record=record,
    )
    dispatch_communication_rules(db, ctx)


def dispatch_record_created_rules(
    db: Session,
    *,
    project: Project,
    actor_user_id: uuid.UUID,
    record: ProjectRecord,
) -> None:
    ctx = CommunicationContext(
        event="on_record_created",
        project=project,
        author_id=actor_user_id,
        entity_type=record.record_type,
        record_type=record.record_type,
        entity_id=record.id,
        record=record,
    )
    dispatch_communication_rules(db, ctx)


def dispatch_feature_block_rules(
    db: Session,
    *,
    project: Project,
    feature: ProjectRecord,
    actor_user_id: uuid.UUID,
    blocked: bool,
) -> None:
    dispatch_state_entered_rules(
        db,
        project=project,
        actor_user_id=actor_user_id,
        record=feature,
        to_state="bloqueada" if blocked else "desbloqueada",
    )
