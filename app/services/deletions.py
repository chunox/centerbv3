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
    Feature,
    FeatureQuery,
    FeatureReport,
    Milestone,
    Project,
    Task,
)
from app.services.access import assert_member_has_role, assert_project_active
from app.services.audit import record_audit_log


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

    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="milestone",
        entidad_id=milestone.id,
        accion="deleted",
    )
    db.delete(milestone)


def delete_project(
    db: Session,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_member_has_role(db, project.id, actor_user_id, "pm")

    feature_ids = list(
        db.scalars(select(Feature.id).where(Feature.project_id == project.id))
    )
    task_ids = list(
        db.scalars(select(Task.id).where(Task.project_id == project.id))
    )
    milestone_ids = list(
        db.scalars(select(Milestone.id).where(Milestone.project_id == project.id))
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

    for milestone in list(project.milestones):
        db.delete(milestone)
    db.flush()
    db.execute(delete(Task).where(Task.project_id == project.id))
    db.execute(delete(Feature).where(Feature.project_id == project.id))
    db.execute(delete(AuditLog).where(AuditLog.project_id == project.id))
    db.delete(project)
