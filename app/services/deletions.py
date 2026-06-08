"""Borrado en cascada de proyecto e hito (§4.2, §4.4)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.entities import (
    Attachment,
    AttachmentRelation,
    AuditLog,
    Comment,
    Feature,
    FeatureQuery,
    FeatureReport,
    Milestone,
    Project,
    Task,
)
from app.services.access import (
    assert_member_has_role,
    assert_pm_or_org_admin_of_project,
    assert_project_active,
)
from app.services.audit import record_audit_log
from app.services.milestones import compact_milestone_ordenes


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


def _break_feature_report_cycles(
    db: Session,
    *,
    feature_ids: list[uuid.UUID],
    report_ids: list[uuid.UUID],
) -> None:
    """Rompe FKs circulares feature ↔ report antes de borrar en bulk."""
    if feature_ids:
        db.execute(
            update(Feature)
            .where(Feature.id.in_(feature_ids))
            .values(origen_report_id=None, origen_feature_id=None)
        )
    if report_ids:
        db.execute(
            update(FeatureReport)
            .where(FeatureReport.id.in_(report_ids))
            .values(generated_feature_id=None)
        )


def _bulk_delete_feature_graph(
    db: Session,
    *,
    feature_ids: list[uuid.UUID],
    task_ids: list[uuid.UUID],
    query_ids: list[uuid.UUID],
    report_ids: list[uuid.UUID],
) -> None:
    _break_feature_report_cycles(
        db, feature_ids=feature_ids, report_ids=report_ids
    )
    if query_ids:
        db.execute(delete(FeatureQuery).where(FeatureQuery.id.in_(query_ids)))
    if report_ids:
        db.execute(delete(FeatureReport).where(FeatureReport.id.in_(report_ids)))
    if task_ids:
        db.execute(delete(Task).where(Task.id.in_(task_ids)))
    if feature_ids:
        db.execute(delete(Feature).where(Feature.id.in_(feature_ids)))


def delete_milestone(
    db: Session,
    milestone: Milestone,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_project_active(project)
    assert_member_has_role(db, project.id, actor_user_id, "pm")

    feature_ids = list(
        db.scalars(select(Feature.id).where(Feature.milestone_id == milestone.id))
    )
    task_ids = list(
        db.scalars(select(Task.id).where(Task.feature_id.in_(feature_ids)))
        if feature_ids
        else []
    )
    query_ids = list(
        db.scalars(
            select(FeatureQuery.id).where(FeatureQuery.feature_id.in_(feature_ids))
        )
        if feature_ids
        else []
    )
    report_ids = list(
        db.scalars(
            select(FeatureReport.id).where(FeatureReport.feature_id.in_(feature_ids))
        )
        if feature_ids
        else []
    )

    for tipo, ids in (
        ("tarea", task_ids),
        ("feature", feature_ids),
        ("feature_query", query_ids),
        ("feature_report", report_ids),
    ):
        _delete_polymorphic_for_ids(db, entidad_tipo=tipo, entidad_ids=ids)

    _bulk_delete_feature_graph(
        db,
        feature_ids=feature_ids,
        task_ids=task_ids,
        query_ids=query_ids,
        report_ids=report_ids,
    )

    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="milestone",
        entidad_id=milestone.id,
        accion="deleted",
    )
    db.execute(delete(Milestone).where(Milestone.id == milestone.id))
    compact_milestone_ordenes(db, project.id)


def delete_project(
    db: Session,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_pm_or_org_admin_of_project(db, project, actor_user_id)

    project_id = project.id
    feature_ids = list(
        db.scalars(select(Feature.id).where(Feature.project_id == project_id))
    )
    task_ids = list(
        db.scalars(select(Task.id).where(Task.project_id == project_id))
    )
    milestone_ids = list(
        db.scalars(select(Milestone.id).where(Milestone.project_id == project_id))
    )
    query_ids = list(
        db.scalars(
            select(FeatureQuery.id).where(FeatureQuery.feature_id.in_(feature_ids))
        )
        if feature_ids
        else []
    )
    report_ids = list(
        db.scalars(
            select(FeatureReport.id).where(FeatureReport.feature_id.in_(feature_ids))
        )
        if feature_ids
        else []
    )

    for tipo, ids in (
        ("tarea", task_ids),
        ("feature", feature_ids),
        ("milestone", milestone_ids),
        ("feature_query", query_ids),
        ("feature_report", report_ids),
    ):
        _delete_polymorphic_for_ids(db, entidad_tipo=tipo, entidad_ids=ids)

    _bulk_delete_feature_graph(
        db,
        feature_ids=feature_ids,
        task_ids=task_ids,
        query_ids=query_ids,
        report_ids=report_ids,
    )
    if milestone_ids:
        db.execute(delete(Milestone).where(Milestone.id.in_(milestone_ids)))
    db.execute(delete(AuditLog).where(AuditLog.project_id == project_id))

    db.expire(project, ["milestones", "features", "tasks"])
    db.delete(project)
