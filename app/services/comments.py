"""Comentarios polimórficos con menciones @uuid (§4.9)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from sqlalchemy import select

from app.models.entities import (
    Comment,
    FeatureQuery,
    FeatureReport,
    Project,
    ProjectMember,
    User,
)
from app.schemas.comments import CommentCreate
from app.services.access import (
    assert_member_of_project,
    assert_project_active,
    get_project_id_for_comment_entity,
    parse_mention_user_ids,
)
from app.services.audit import record_audit_log
from app.services.notifications import create_notification

CLIENTE_QUERY_STATES = frozenset({"esperando_cliente", "respuesta_cliente"})


def _notify_thread_participants(
    db: Session,
    *,
    project: Project,
    author_id: uuid.UUID,
    entidad_tipo: str,
    entidad_id: uuid.UUID,
    mentioned_ids: set[uuid.UUID],
) -> None:
    if entidad_tipo not in ("feature_query", "feature_report"):
        return

    from app.domain.capabilities import WORKBENCH_INBOX_CLIENT, WORKBENCH_INBOX_PM
    from app.services.workflow.capabilities import users_with_capability

    recipients: set[uuid.UUID] = set(
        users_with_capability(db, project.id, WORKBENCH_INBOX_PM)
    )

    if entidad_tipo == "feature_report":
        report = db.get(FeatureReport, entidad_id)
        if report:
            recipients.add(report.reported_by)
    else:
        query = db.get(FeatureQuery, entidad_id)
        if query:
            recipients.add(query.created_by)
            if (
                project.tipo in ("con_cliente", "freestyle")
                and query.estado in CLIENTE_QUERY_STATES
            ):
                recipients.update(
                    users_with_capability(db, project.id, WORKBENCH_INBOX_CLIENT)
                )

    recipients.discard(author_id)
    recipients -= mentioned_ids

    for user_id in recipients:
        create_notification(
            db,
            user_id=user_id,
            project_id=project.id,
            tipo="comentario_nuevo",
            entidad_tipo=entidad_tipo,  # type: ignore[arg-type]
            entidad_id=entidad_id,
        )


def create_comment(
    db: Session,
    payload: CommentCreate,
) -> Comment:
    project_id = get_project_id_for_comment_entity(
        db, payload.entidad_tipo, payload.entidad_id
    )
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    assert_project_active(project)
    assert_member_of_project(db, project_id, payload.user_id)

    author = db.get(User, payload.user_id)
    if not author:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    comment = Comment(**payload.model_dump())
    db.add(comment)
    db.flush()

    record_audit_log(
        db,
        project_id=project_id,
        user_id=payload.user_id,
        entidad_tipo="comment",
        entidad_id=comment.id,
        accion="created",
        campo=payload.entidad_tipo,
        valor_nuevo=str(payload.entidad_id),
    )

    notif_entidad_map = {
        "feature": "feature",
        "tarea": "tarea",
        "feature_query": "feature_query",
        "feature_report": "feature_report",
    }
    mentioned_ids: set[uuid.UUID] = set()
    for mentioned_id in parse_mention_user_ids(payload.contenido):
        if mentioned_id == payload.user_id:
            continue
        mentioned_ids.add(mentioned_id)
        assert_member_of_project(db, project_id, mentioned_id)
        create_notification(
            db,
            user_id=mentioned_id,
            project_id=project_id,
            tipo="mencionado",
            entidad_tipo=notif_entidad_map[payload.entidad_tipo],  # type: ignore[arg-type]
            entidad_id=payload.entidad_id,
        )

    _notify_thread_participants(
        db,
        project=project,
        author_id=payload.user_id,
        entidad_tipo=payload.entidad_tipo,
        entidad_id=payload.entidad_id,
        mentioned_ids=mentioned_ids,
    )

    return comment
