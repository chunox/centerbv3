"""Borrado en cascada de proyecto e hito (§4.2, §4.4)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Attachment,
    AttachmentRelation,
    AuditLog,
    Comment,
    Project,
    ProjectRecord,
    ProjectRecordAssignee,
    ProjectRecordDependency,
)
from app.domain.capabilities import SCOPE_MILESTONE_DELETE
from app.services.access import (
    assert_pm_or_org_admin_of_project,
    assert_project_active,
)
from app.services.workflow.authorize import assert_capability
from app.services.audit import record_audit_log
from app.services.milestones import compact_milestone_ordenes
from app.services.records.repository import list_children, list_records, set_field


def _delete_polymorphic_for_ids(
    db: Session,
    *,
    entidad_tipo: str,
    entidad_ids: list[uuid.UUID],
) -> None:
    if not entidad_ids:
        return
    db.execute(
        delete(Comment).where(
            Comment.entidad_tipo == entidad_tipo,
            Comment.entidad_id.in_(entidad_ids),
        )
    )
    relation_ids = list(
        db.scalars(
            select(AttachmentRelation.attachment_id).where(
                AttachmentRelation.entidad_tipo == entidad_tipo,
                AttachmentRelation.entidad_id.in_(entidad_ids),
            )
        )
    )
    if relation_ids:
        db.execute(
            delete(AttachmentRelation).where(
                AttachmentRelation.attachment_id.in_(relation_ids)
            )
        )
        for att_id in set(relation_ids):
            remaining = db.scalar(
                select(AttachmentRelation.id)
                .where(AttachmentRelation.attachment_id == att_id)
                .limit(1)
            )
            if remaining is None:
                attachment = db.get(Attachment, att_id)
                if attachment:
                    db.delete(attachment)


def _break_feature_report_cycles_records(
    db: Session,
    *,
    features: list[ProjectRecord],
    reports: list[ProjectRecord],
) -> None:
    for feature in features:
        set_field(feature, "origen_report_id", None)
        set_field(feature, "origen_feature_id", None)
    for report in reports:
        set_field(report, "generated_feature_id", None)


def _delete_record_graph(
    db: Session,
    *,
    feature_ids: list[uuid.UUID],
    task_ids: list[uuid.UUID],
    query_ids: list[uuid.UUID],
    report_ids: list[uuid.UUID],
    features: list[ProjectRecord],
    reports: list[ProjectRecord],
) -> None:
    _break_feature_report_cycles_records(
        db, features=features, reports=reports
    )

    all_ids = set(task_ids + query_ids + report_ids + feature_ids)
    if all_ids:
        db.execute(
            delete(ProjectRecordAssignee).where(
                ProjectRecordAssignee.record_id.in_(all_ids)
            )
        )
        db.execute(
            delete(ProjectRecordDependency).where(
                ProjectRecordDependency.successor_id.in_(all_ids)
                | ProjectRecordDependency.predecessor_id.in_(all_ids)
            )
        )

    for record_id in task_ids + query_ids + report_ids + feature_ids:
        row = db.get(ProjectRecord, record_id)
        if row is not None:
            db.delete(row)


def _collect_milestone_descendants(
    db: Session, milestone_id: uuid.UUID
) -> tuple[
    list[ProjectRecord],
    list[uuid.UUID],
    list[uuid.UUID],
    list[uuid.UUID],
    list[uuid.UUID],
    list[ProjectRecord],
]:
    features = list_children(db, milestone_id, "feature")
    feature_ids = [f.id for f in features]
    task_ids: list[uuid.UUID] = []
    query_ids: list[uuid.UUID] = []
    report_ids: list[uuid.UUID] = []
    reports: list[ProjectRecord] = []

    for feature in features:
        task_ids.extend(t.id for t in list_children(db, feature.id, "task"))
        query_ids.extend(q.id for q in list_children(db, feature.id, "query"))
        feature_reports = list_children(db, feature.id, "report")
        reports.extend(feature_reports)
        report_ids.extend(r.id for r in feature_reports)

    return features, feature_ids, task_ids, query_ids, report_ids, reports


def delete_milestone(
    db: Session,
    milestone: ProjectRecord,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_project_active(project)
    assert_capability(db, project.id, actor_user_id, SCOPE_MILESTONE_DELETE)

    features, feature_ids, task_ids, query_ids, report_ids, reports = (
        _collect_milestone_descendants(db, milestone.id)
    )

    for tipo, ids in (
        ("tarea", task_ids),
        ("feature", feature_ids),
        ("feature_query", query_ids),
        ("feature_report", report_ids),
    ):
        _delete_polymorphic_for_ids(db, entidad_tipo=tipo, entidad_ids=ids)

    _delete_record_graph(
        db,
        feature_ids=feature_ids,
        task_ids=task_ids,
        query_ids=query_ids,
        report_ids=report_ids,
        features=features,
        reports=reports,
    )

    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="milestone",
        entidad_id=milestone.id,
        accion="deleted",
    )
    db.delete(milestone)
    compact_milestone_ordenes(db, project.id)


def delete_project(
    db: Session,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_pm_or_org_admin_of_project(db, project, actor_user_id)

    project_id = project.id
    all_rows = list_records(db, project_id)
    milestones = [r for r in all_rows if r.record_type == "milestone"]
    features = [r for r in all_rows if r.record_type == "feature"]
    tasks = [r for r in all_rows if r.record_type == "task"]
    queries = [r for r in all_rows if r.record_type == "query"]
    reports = [r for r in all_rows if r.record_type == "report"]

    milestone_ids = [m.id for m in milestones]
    feature_ids = [f.id for f in features]
    task_ids = [t.id for t in tasks]
    query_ids = [q.id for q in queries]
    report_ids = [r.id for r in reports]

    for tipo, ids in (
        ("tarea", task_ids),
        ("feature", feature_ids),
        ("milestone", milestone_ids),
        ("feature_query", query_ids),
        ("feature_report", report_ids),
    ):
        _delete_polymorphic_for_ids(db, entidad_tipo=tipo, entidad_ids=ids)

    _delete_record_graph(
        db,
        feature_ids=feature_ids,
        task_ids=task_ids,
        query_ids=query_ids,
        report_ids=report_ids,
        features=features,
        reports=reports,
    )

    for milestone in milestones:
        row = db.get(ProjectRecord, milestone.id)
        if row is not None:
            db.delete(row)

    db.execute(delete(AuditLog).where(AuditLog.project_id == project_id))
    db.delete(project)
