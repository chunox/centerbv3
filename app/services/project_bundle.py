"""Agregación servidor del bundle de proyecto (BFF)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AuditLog, Project, ProjectRecordDependency, ProjectRecordType
from app.services.audit_display import audit_logs_to_read
from app.schemas.project_bundle import (
    BundleFeatureQueryRead,
    BundleFeatureReportRead,
    FeatureContextEntryRead,
    ProjectBundleRead,
)
from app.schemas.task_dependencies import TaskDependencyRead
from app.schemas.projects import ProjectRead
from app.services.access import resolve_audit_logs_for_user
from app.services.records.mappers import (
    record_to_feature_read,
    record_to_milestone_read,
    record_to_query_read,
    record_to_read,
    record_to_report_read,
    record_to_task_read,
)
from app.services.records.repository import list_assignee_ids, list_dependencies, list_records

_PENDING_QUERY_STATES = frozenset(
    {"borrador", "pendiente_aprobacion_pm", "esperando_pm", "respuesta_cliente"}
)


def _dependency_to_read(
    dep: ProjectRecordDependency,
    *,
    created_by: UUID,
) -> TaskDependencyRead:
    return TaskDependencyRead(
        id=dep.id,
        project_id=dep.project_id,
        task_id=dep.successor_id,
        depends_on_task_id=dep.predecessor_id,
        created_by=created_by,
        created_at=dep.created_at,
    )


def build_project_bundle(
    db: Session,
    project: Project,
    *,
    viewer_user_id: UUID | None = None,
) -> ProjectBundleRead:
    all_rows = list_records(db, project.id)
    milestones = [r for r in all_rows if r.record_type == "milestone"]
    features = [r for r in all_rows if r.record_type == "feature"]
    tasks = [r for r in all_rows if r.record_type == "task"]
    reports = [r for r in all_rows if r.record_type == "report"]
    queries = [r for r in all_rows if r.record_type == "query"]
    task_dependencies = list_dependencies(db, project.id)

    record_types = [
        rt.key
        for rt in db.scalars(
            select(ProjectRecordType)
            .where(ProjectRecordType.project_id == project.id)
            .order_by(ProjectRecordType.orden.asc())
        )
    ]

    records_by_type: dict[str, list] = {}
    children_by_parent: dict[str, list] = {}
    for row in all_rows:
        read = record_to_read(row, list_assignee_ids(db, row))
        records_by_type.setdefault(row.record_type, []).append(read)
        if row.parent_id is not None:
            children_by_parent.setdefault(str(row.parent_id), []).append(read)

    milestone_by_id = {m.id: m for m in milestones}
    feature_by_id = {f.id: f for f in features}
    task_by_id = {t.id: t for t in tasks}

    features_by_milestone: dict[str, list] = {}
    feature_context: dict[str, FeatureContextEntryRead] = {}
    for feature in features:
        mid = str(feature.parent_id)
        feature_read = record_to_feature_read(feature)
        features_by_milestone.setdefault(mid, []).append(feature_read)
        milestone = milestone_by_id.get(feature.parent_id)
        feature_context[str(feature.id)] = FeatureContextEntryRead(
            milestone_id=feature.parent_id,
            milestone_nombre=milestone.titulo if milestone else "",
            feature=feature_read,
        )

    tasks_by_feature: dict[str, list] = {}
    for task in tasks:
        tasks_by_feature.setdefault(str(task.parent_id), []).append(
            record_to_task_read(task, list_assignee_ids(db, task))
        )

    enriched_reports: list[BundleFeatureReportRead] = []
    for report in reports:
        feature = feature_by_id.get(report.parent_id)
        enriched_reports.append(
            BundleFeatureReportRead(
                **record_to_report_read(report).model_dump(),
                feature_nombre=feature.titulo if feature else None,
                milestone_id=feature.parent_id if feature else None,
            )
        )

    enriched_queries: list[BundleFeatureQueryRead] = []
    for query in queries:
        feature = feature_by_id.get(query.parent_id)
        enriched_queries.append(
            BundleFeatureQueryRead(
                **record_to_query_read(query).model_dump(),
                feature_nombre=feature.titulo if feature else None,
                milestone_id=feature.parent_id if feature else None,
            )
        )

    audit_stmt = (
        select(AuditLog)
        .where(AuditLog.project_id == project.id)
        .order_by(AuditLog.created_at.desc())
        .limit(500)
    )
    audit_logs = resolve_audit_logs_for_user(
        db,
        list(db.scalars(audit_stmt)),
        project_id=project.id,
        viewer_user_id=viewer_user_id,
    )

    release_count = sum(
        1 for f in features if f.estado == "esperando_liberacion_pm"
    )
    pending_reports = sum(1 for r in reports if r.estado == "pendiente")
    pending_queries = sum(1 for q in queries if q.estado in _PENDING_QUERY_STATES)
    inbox_action_count = pending_reports + pending_queries + release_count

    return ProjectBundleRead(
        project=ProjectRead.model_validate(project),
        record_types=record_types,
        records_by_type=records_by_type,
        children_by_parent=children_by_parent,
        milestones=[record_to_milestone_read(m) for m in milestones],
        features_by_milestone=features_by_milestone,
        tasks_by_feature=tasks_by_feature,
        feature_context=feature_context,
        reports=enriched_reports,
        queries=enriched_queries,
        audit_logs=audit_logs_to_read(db, audit_logs),
        inbox_action_count=inbox_action_count,
        task_dependencies=[
            _dependency_to_read(
                dep,
                created_by=task_by_id[dep.successor_id].created_by
                if dep.successor_id in task_by_id
                else dep.id,
            )
            for dep in task_dependencies
        ],
    )
