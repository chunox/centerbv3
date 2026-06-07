"""Comentarios polimórficos con menciones @uuid (§4.9)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Comment, Project, User
from app.schemas.comments import CommentCreate
from app.services.access import (
    assert_member_of_project,
    assert_project_active,
    get_project_id_for_comment_entity,
    parse_mention_user_ids,
)
from app.services.audit import record_audit_log
from app.services.notifications import create_notification


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
    )

    notif_entidad_map = {
        "feature": "feature",
        "tarea": "tarea",
        "feature_query": "feature_query",
        "feature_report": "feature_report",
    }
    for mentioned_id in parse_mention_user_ids(payload.contenido):
        if mentioned_id == payload.user_id:
            continue
        assert_member_of_project(db, project_id, mentioned_id)
        create_notification(
            db,
            user_id=mentioned_id,
            project_id=project_id,
            tipo="mencionado",
            entidad_tipo=notif_entidad_map[payload.entidad_tipo],  # type: ignore[arg-type]
            entidad_id=payload.entidad_id,
        )

    return comment
