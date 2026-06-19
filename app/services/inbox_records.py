"""Registros visibles en bandejas por rol (alineado con inbox-summary)."""
from __future__ import annotations

import json
import uuid
from typing import Literal

from sqlalchemy.orm import Session

from app.domain.project_mode import is_software_work_item
from app.models.entities import Project, ProjectRecord
from app.services.records.repository import list_records

InboxQueue = Literal["pm", "client", "dev", "qa"]

# Conteo sidebar PM: reportes pendientes + consultas accionables por PM + liberaciones.
PM_INBOX_QUERY_STATES = frozenset(
    {"borrador", "pendiente_aprobacion_pm", "esperando_pm", "respuesta_cliente"}
)
# Incluye esperando_cliente para métricas amplias / legacy.
PM_INBOX_QUERY_STATES_BROAD = PM_INBOX_QUERY_STATES | frozenset({"esperando_cliente"})

CLIENT_INBOX_QUERY_STATES = frozenset({"esperando_cliente", "respuesta_cliente"})
CLIENT_VALIDATION_FEATURE_STATES = frozenset({"liberado_cliente", "esperando_validacion_cliente"})


def _record_data(record: ProjectRecord) -> dict:
    raw = record.data
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def is_pm_inbox_record(record: ProjectRecord) -> bool:
    if record.record_type == "report":
        return record.estado == "pendiente"
    if record.record_type == "query":
        return record.estado in PM_INBOX_QUERY_STATES
    if is_software_work_item(record):
        return record.estado == "esperando_liberacion_pm"
    return False


def is_client_inbox_record(record: ProjectRecord) -> bool:
    if record.record_type == "query":
        return record.estado in CLIENT_INBOX_QUERY_STATES
    if is_software_work_item(record):
        return record.estado in CLIENT_VALIDATION_FEATURE_STATES
    if record.record_type == "report":
        return record.estado == "pendiente"
    return False


def is_dev_inbox_record(record: ProjectRecord, actor_user_id: uuid.UUID | None = None) -> bool:
    if record.record_type != "query":
        return False
    if actor_user_id is None:
        return True
    return record.created_by == actor_user_id


def is_qa_inbox_record(record: ProjectRecord, actor_user_id: uuid.UUID | None = None) -> bool:
    return is_dev_inbox_record(record, actor_user_id)


def _match_queue(
    record: ProjectRecord,
    queue: InboxQueue,
    actor_user_id: uuid.UUID | None = None,
) -> bool:
    if queue == "pm":
        return is_pm_inbox_record(record)
    if queue == "client":
        return is_client_inbox_record(record)
    if queue == "dev":
        return is_dev_inbox_record(record, actor_user_id)
    if queue == "qa":
        return is_qa_inbox_record(record, actor_user_id)
    return False


def list_inbox_records(
    db: Session,
    project: Project,
    queue: InboxQueue | None = None,
    *,
    workbench_key: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> list[ProjectRecord]:
    if workbench_key:
        from app.services.inbox_queue_filter import list_inbox_records_for_workbench

        return list_inbox_records_for_workbench(
            db, project, workbench_key, actor_user_id=actor_user_id
        )
    if queue is None:
        return []
    rows = list_records(db, project.id)
    matched = [r for r in rows if _match_queue(r, queue, actor_user_id)]
    matched.sort(key=lambda r: (r.updated_at, r.created_at), reverse=True)
    return matched


def count_pm_inbox_actionables(
    reports: list[ProjectRecord],
    queries: list[ProjectRecord],
    features: list[ProjectRecord],
) -> tuple[int, int, int, int]:
    pending_reports = sum(1 for r in reports if r.estado == "pendiente")
    pending_queries = sum(1 for q in queries if q.estado in PM_INBOX_QUERY_STATES)
    pending_releases = sum(
        1 for f in features if f.estado == "esperando_liberacion_pm"
    )
    inbox_action_count = pending_reports + pending_queries + pending_releases
    return inbox_action_count, pending_reports, pending_queries, pending_releases
