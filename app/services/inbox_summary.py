"""Conteos ligeros de bandeja para sidebar (sin bundle monolítico)."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.entities import Project
from app.schemas.inbox_summary import ProjectInboxSummaryRead
from app.services.inbox_queue_filter import build_counts_by_workbench
from app.services.inbox_records import count_pm_inbox_actionables
from app.services.records.repository import list_records


def build_inbox_summary(
    db: Session,
    project: Project,
    *,
    viewer_user_id: uuid.UUID | None = None,
) -> ProjectInboxSummaryRead:
    all_rows = list_records(db, project.id)
    features = [r for r in all_rows if r.record_type == "feature"]
    reports = [r for r in all_rows if r.record_type == "report"]
    queries = [r for r in all_rows if r.record_type == "query"]

    counts_by_workbench = build_counts_by_workbench(
        db, project, actor_user_id=viewer_user_id
    )

    inbox_action_count = counts_by_workbench.get("inbox_pm")
    client_inbox_count = counts_by_workbench.get("inbox_client")
    if inbox_action_count is None or client_inbox_count is None:
        legacy_count, pending_reports, pending_queries, pending_releases = (
            count_pm_inbox_actionables(reports, queries, features)
        )
        inbox_action_count = inbox_action_count if inbox_action_count is not None else legacy_count
        if client_inbox_count is None:
            from app.services.inbox_records import (
                CLIENT_INBOX_QUERY_STATES,
                CLIENT_VALIDATION_FEATURE_STATES,
            )

            client_pending_queries = sum(
                1 for q in queries if q.estado in CLIENT_INBOX_QUERY_STATES
            )
            pending_validations = sum(
                1 for f in features if f.estado in CLIENT_VALIDATION_FEATURE_STATES
            )
            client_inbox_count = client_pending_queries + pending_validations

    if project.pack_slug == "marketing360":
        aprobaciones = counts_by_workbench.get("aprobaciones")
        if aprobaciones is not None:
            client_inbox_count = aprobaciones

    _, pending_reports, pending_queries, pending_releases = count_pm_inbox_actionables(
        reports, queries, features
    )
    from app.services.inbox_records import CLIENT_VALIDATION_FEATURE_STATES

    pending_validations = sum(
        1 for f in features if f.estado in CLIENT_VALIDATION_FEATURE_STATES
    )

    return ProjectInboxSummaryRead(
        inbox_action_count=inbox_action_count or 0,
        client_inbox_count=client_inbox_count or 0,
        pending_reports=pending_reports,
        pending_queries=pending_queries,
        pending_releases=pending_releases,
        pending_validations=pending_validations,
        counts_by_workbench=counts_by_workbench,
    )
