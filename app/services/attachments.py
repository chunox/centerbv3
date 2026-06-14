"""Creación de adjuntos y vínculo a entidades (§4.11)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import (
    Attachment,
    AttachmentRelation,
    Comment,
    Document,
    HubEntry,
    ProjectRecord,
    User,
)
from app.models.entities import Project
from app.schemas.attachments import AttachmentEntidadTipo, AttachmentUpdate
from app.services.access import (
    assert_attachment_author_or_pm,
    assert_member_of_project,
    assert_pm_or_dev_member,
    assert_project_active,
    get_project_id_for_attachment_entity,
)
from app.services.audit import record_audit_log
from app.services.file_storage import (
    is_stored_attachment,
    rename_stored_file,
    delete_attachment_storage,
)

_ENTITY_GETTERS: dict[AttachmentEntidadTipo, type] = {
    "comment": Comment,
    "document": Document,
    "hub_entry": HubEntry,
    "project": Project,
}

_RECORD_ENTITY_TYPES: dict[AttachmentEntidadTipo, str] = {
    "tarea": "task",
    "feature": "feature",
    "feature_query": "query",
    "feature_report": "report",
    "pieza": "pieza",
    "entregable": "entregable",
    "campana": "campana",
}


def _assert_hub_attachment_mutation(
    db: Session,
    *,
    entidad_tipo: AttachmentEntidadTipo,
    project: Project,
    actor_user_id: uuid.UUID,
) -> None:
    if entidad_tipo in ("hub_entry", "project"):
        assert_pm_or_dev_member(db, project.id, actor_user_id)


def ensure_attachment_entidad_exists(
    entidad_tipo: AttachmentEntidadTipo,
    entidad_id: uuid.UUID,
    db: Session,
) -> None:
    record_type = _RECORD_ENTITY_TYPES.get(entidad_tipo)
    if record_type:
        row = db.get(ProjectRecord, entidad_id)
        if not row or row.record_type != record_type:
            raise HTTPException(
                status_code=404,
                detail=f"No existe {entidad_tipo} con id {entidad_id}",
            )
        return
    model = _ENTITY_GETTERS[entidad_tipo]
    if not db.get(model, entidad_id):
        raise HTTPException(
            status_code=404,
            detail=f"No existe {entidad_tipo} con id {entidad_id}",
        )


def _project_for_attachment_entity(
    db: Session,
    *,
    entidad_tipo: AttachmentEntidadTipo,
    entidad_id: uuid.UUID,
) -> Project:
    project_id = get_project_id_for_attachment_entity(db, entidad_tipo, entidad_id)
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return project


def assert_attachment_read_allowed(
    db: Session,
    *,
    entidad_tipo: AttachmentEntidadTipo,
    entidad_id: uuid.UUID,
    viewer_user_id: uuid.UUID,
) -> None:
    project = _project_for_attachment_entity(
        db, entidad_tipo=entidad_tipo, entidad_id=entidad_id
    )
    assert_member_of_project(db, project.id, viewer_user_id)


def _assert_attachment_mutation_allowed(
    db: Session,
    *,
    entidad_tipo: AttachmentEntidadTipo,
    entidad_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Project:
    project = _project_for_attachment_entity(
        db, entidad_tipo=entidad_tipo, entidad_id=entidad_id
    )
    assert_project_active(project)
    assert_member_of_project(db, project.id, actor_user_id)
    _assert_hub_attachment_mutation(
        db, entidad_tipo=entidad_tipo, project=project, actor_user_id=actor_user_id
    )
    return project


def _assert_attachment_edit_allowed(
    db: Session,
    attachment: Attachment,
    actor_user_id: uuid.UUID,
) -> Project:
    relation = attachment.relations[0] if attachment.relations else None
    if relation is None:
        raise HTTPException(status_code=409, detail="Adjunto sin entidad vinculada")
    project = _assert_attachment_mutation_allowed(
        db,
        entidad_tipo=relation.entidad_tipo,  # type: ignore[arg-type]
        entidad_id=relation.entidad_id,
        actor_user_id=actor_user_id,
    )
    assert_attachment_author_or_pm(
        db,
        project.id,
        actor_user_id,
        uploaded_by=attachment.uploaded_by,
    )
    return project


def create_attachment_for_entity(
    db: Session,
    *,
    url: str,
    nombre_original: str,
    mime_type: str,
    tamano_bytes: int,
    uploaded_by: uuid.UUID,
    entidad_tipo: AttachmentEntidadTipo,
    entidad_id: uuid.UUID,
    attachment_id: uuid.UUID | None = None,
) -> Attachment:
    ensure_attachment_entidad_exists(entidad_tipo, entidad_id, db)
    project = _assert_attachment_mutation_allowed(
        db,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        actor_user_id=uploaded_by,
    )
    uploader = db.get(User, uploaded_by)
    if not uploader:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    attachment = Attachment(
        id=attachment_id or uuid.uuid4(),
        url=url,
        nombre_original=nombre_original,
        mime_type=mime_type,
        tamano_bytes=tamano_bytes,
        uploaded_by=uploaded_by,
    )
    relation = AttachmentRelation(
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
    )
    attachment.relations.append(relation)
    db.add(attachment)
    db.flush()
    record_audit_log(
        db,
        project_id=project.id,
        user_id=uploaded_by,
        entidad_tipo="document",
        entidad_id=attachment.id,
        accion="created",
    )
    return attachment


def update_attachment(
    db: Session,
    attachment: Attachment,
    payload: AttachmentUpdate,
) -> None:
    project = _assert_attachment_edit_allowed(db, attachment, payload.actor_user_id)

    changes = payload.model_dump(exclude_unset=True, exclude={"actor_user_id"})
    if not changes:
        return

    stored = is_stored_attachment(attachment.url)
    if stored and changes.get("url") is not None:
        raise HTTPException(
            status_code=409,
            detail="No se puede cambiar la URL de un adjunto subido por upload",
        )

    nombre_anterior = attachment.nombre_original
    for field, nuevo in changes.items():
        anterior = getattr(attachment, field)
        if anterior == nuevo:
            continue
        setattr(attachment, field, nuevo)
        record_audit_log(
            db,
            project_id=project.id,
            user_id=payload.actor_user_id,
            entidad_tipo="document",
            entidad_id=attachment.id,
            accion="updated",
            campo=field,
            valor_anterior=str(anterior),
            valor_nuevo=str(nuevo),
        )

    if stored and "nombre_original" in changes:
        rename_stored_file(
            attachment.id,
            nombre_anterior,
            attachment.nombre_original,
        )


def delete_attachment(
    db: Session,
    attachment: Attachment,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    relation = attachment.relations[0] if attachment.relations else None
    project_id = None
    if relation is not None:
        project = _assert_attachment_edit_allowed(db, attachment, actor_user_id)
        project_id = project.id
        record_audit_log(
            db,
            project_id=project.id,
            user_id=actor_user_id,
            entidad_tipo="document",
            entidad_id=attachment.id,
            accion="deleted",
        )

    stored = is_stored_attachment(attachment.url)
    attachment_id = attachment.id
    db.delete(attachment)
    if stored:
        delete_attachment_storage(attachment_id)
