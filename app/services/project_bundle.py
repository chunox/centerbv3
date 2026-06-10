"""Agregación servidor del bundle de proyecto (BFF)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    AuditLog,
    Feature,
    FeatureQuery,
    FeatureReport,
    Milestone,
    Project,
    Task,
    TaskDependency,
)
from app.services.audit_display import audit_logs_to_read
from app.schemas.feature_queries import FeatureQueryRead
from app.schemas.feature_reports import FeatureReportRead
from app.schemas.project_bundle import (
    BundleFeatureQueryRead,
    BundleFeatureReportRead,
    FeatureContextEntryRead,
    ProjectBundleRead,
)
from app.schemas.features import FeatureRead
from app.schemas.task_dependencies import TaskDependencyRead
from app.schemas.milestones import MilestoneRead
from app.schemas.projects import ProjectRead
from app.schemas.tasks import TaskRead
from app.services.access import resolve_audit_logs_for_user

_PENDING_QUERY_STATES = frozenset(
    {"borrador", "pendiente_aprobacion_pm", "esperando_pm", "respuesta_cliente"}
)


def build_project_bundle(
    db: Session,
    project: Project,
    *,
    viewer_user_id: UUID | None = None,
) -> ProjectBundleRead:
    milestones = list(
        db.scalars(
            select(Milestone)
            .where(Milestone.project_id == project.id)
            .order_by(Milestone.orden, Milestone.fecha_inicio)
        )
    )
    features = list(
        db.scalars(select(Feature).where(Feature.project_id == project.id))
    )
    tasks = list(db.scalars(select(Task).where(Task.project_id == project.id)))
    task_dependencies = list(
        db.scalars(
            select(TaskDependency).where(TaskDependency.project_id == project.id)
        )
    )
    feature_ids = [f.id for f in features]
    reports = (
        list(
            db.scalars(
                select(FeatureReport).where(FeatureReport.feature_id.in_(feature_ids))
            )
        )
        if feature_ids
        else []
    )
    queries = (
        list(
            db.scalars(
                select(FeatureQuery).where(FeatureQuery.feature_id.in_(feature_ids))
            )
        )
        if feature_ids
        else []
    )

    milestone_by_id = {m.id: m for m in milestones}
    feature_by_id = {f.id: f for f in features}

    features_by_milestone: dict[str, list[FeatureRead]] = {}
    feature_context: dict[str, FeatureContextEntryRead] = {}
    for feature in features:
        mid = str(feature.milestone_id)
        features_by_milestone.setdefault(mid, []).append(FeatureRead.model_validate(feature))
        milestone = milestone_by_id.get(feature.milestone_id)
        feature_context[str(feature.id)] = FeatureContextEntryRead(
            milestone_id=feature.milestone_id,
            milestone_nombre=milestone.nombre if milestone else "",
            feature=FeatureRead.model_validate(feature),
        )

    tasks_by_feature: dict[str, list[TaskRead]] = {}
    for task in tasks:
        tasks_by_feature.setdefault(str(task.feature_id), []).append(
            TaskRead.model_validate(task)
        )

    enriched_reports: list[BundleFeatureReportRead] = []
    for report in reports:
        feature = feature_by_id.get(report.feature_id)
        enriched_reports.append(
            BundleFeatureReportRead(
                **FeatureReportRead.model_validate(report).model_dump(),
                feature_nombre=feature.nombre if feature else None,
                milestone_id=feature.milestone_id if feature else None,
            )
        )

    enriched_queries: list[BundleFeatureQueryRead] = []
    for query in queries:
        feature = feature_by_id.get(query.feature_id)
        enriched_queries.append(
            BundleFeatureQueryRead(
                **FeatureQueryRead.model_validate(query).model_dump(),
                feature_nombre=feature.nombre if feature else None,
                milestone_id=feature.milestone_id if feature else None,
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
        milestones=[MilestoneRead.model_validate(m) for m in milestones],
        features_by_milestone=features_by_milestone,
        tasks_by_feature=tasks_by_feature,
        feature_context=feature_context,
        reports=enriched_reports,
        queries=enriched_queries,
        audit_logs=audit_logs_to_read(db, audit_logs),
        inbox_action_count=inbox_action_count,
        task_dependencies=[
            TaskDependencyRead.model_validate(d) for d in task_dependencies
        ],
    )
