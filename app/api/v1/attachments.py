"""
Adjuntos — upload de archivos vinculados a records o hub_entries.
POST /projects/{id}/attachments        — sube el archivo
GET  /attachments/{id}/file            — descarga el archivo
DELETE /attachments/{id}               — elimina attachment + archivo en disco
"""
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_actor_id
from app.api.v1.projects import get_project_or_404
from app.config import settings
from app.database import get_db
from app.models.entities import Attachment, AttachmentRelation, ProjectRecord
from app.services.access import require_project_member

router = APIRouter()


class AttachmentResponse(BaseModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    uploaded_by: str
    created_at: str
    entity_type: str | None = None
    entity_id: str | None = None


def _to_response(a: Attachment, relation: AttachmentRelation | None = None) -> AttachmentResponse:
    return AttachmentResponse(
        id=a.id,
        filename=a.filename,
        mime_type=a.mime_type,
        size_bytes=a.size_bytes,
        uploaded_by=a.uploaded_by,
        created_at=a.created_at.isoformat(),
        entity_type=relation.entity_type if relation else None,
        entity_id=relation.entity_id if relation else None,
    )


@router.post("/{project_id}/attachments", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    project_id: str,
    file: UploadFile = File(...),
    entity_type: str = Query("record"),
    entity_id: str = Query(...),
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    project = get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)

    record = db.query(ProjectRecord).filter(
        ProjectRecord.id == str(entity_id),
        ProjectRecord.project_id == str(project_id),
    ).first()
    if entity_type == "record" and not record:
        raise HTTPException(status_code=404, detail="Record no encontrado en el proyecto")

    max_bytes = settings.upload_max_mb * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Archivo demasiado grande (máx {settings.upload_max_mb} MB)")

    upload_dir = os.path.join(settings.upload_dir, str(project.organization_id))
    os.makedirs(upload_dir, exist_ok=True)

    file_id = str(uuid.uuid4())
    safe_ext = os.path.splitext(file.filename or "")[1][:10]
    storage_filename = f"{file_id}{safe_ext}"
    storage_path = os.path.join(upload_dir, storage_filename)

    with open(storage_path, "wb") as f_out:
        f_out.write(content)

    attachment = Attachment(
        organization_id=str(project.organization_id),
        uploaded_by=actor_id,
        filename=file.filename or storage_filename,
        storage_path=storage_path,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
    )
    db.add(attachment)
    db.flush()

    relation = AttachmentRelation(
        attachment_id=attachment.id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(relation)
    db.commit()
    db.refresh(attachment)
    db.refresh(relation)

    return _to_response(attachment, relation)


def _get_attachment_or_404(db: Session, attachment_id: str) -> Attachment:
    attachment = db.query(Attachment).filter(Attachment.id == str(attachment_id)).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return attachment


def _verify_attachment_project_membership(
    db: Session,
    attachment: Attachment,
    actor_id: str,
    *,
    project_id: str | None = None,
) -> None:
    """Verifica que el actor sea miembro del proyecto al que pertenece el adjunto."""
    from app.models.entities import Project, ProjectMember, ProjectRecord, HubEntry

    resolved_project_id = project_id
    if not resolved_project_id:
        relation = (
            db.query(AttachmentRelation)
            .filter(AttachmentRelation.attachment_id == attachment.id)
            .first()
        )
        if relation:
            if relation.entity_type == "record":
                record = db.query(ProjectRecord).filter(ProjectRecord.id == relation.entity_id).first()
                resolved_project_id = str(record.project_id) if record else None
            elif relation.entity_type == "hub_entry":
                entry = db.query(HubEntry).filter(HubEntry.id == relation.entity_id).first()
                resolved_project_id = str(entry.project_id) if entry else None

    if not resolved_project_id:
        raise HTTPException(status_code=403, detail="Sin acceso a este adjunto")

    member = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == str(resolved_project_id),
            ProjectMember.user_id == actor_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="Sin acceso a este adjunto")


@router.get("/attachments/{attachment_id}/file")
def download_attachment(
    attachment_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    attachment = _get_attachment_or_404(db, attachment_id)
    _verify_attachment_project_membership(db, attachment, actor_id)
    if not os.path.exists(attachment.storage_path):
        raise HTTPException(status_code=410, detail="Archivo no disponible")
    return FileResponse(
        path=attachment.storage_path,
        filename=attachment.filename,
        media_type=attachment.mime_type,
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    attachment = _get_attachment_or_404(db, attachment_id)
    _verify_attachment_project_membership(db, attachment, actor_id)
    if attachment.uploaded_by != actor_id:
        raise HTTPException(status_code=403, detail="Solo el uploader puede eliminar este adjunto")
    if os.path.exists(attachment.storage_path):
        os.remove(attachment.storage_path)
    db.delete(attachment)
    db.commit()


@router.get("/{project_id}/records/{record_id}/attachments", response_model=list[AttachmentResponse])
def list_record_attachments(
    project_id: str,
    record_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    rows = (
        db.query(Attachment, AttachmentRelation)
        .join(AttachmentRelation, AttachmentRelation.attachment_id == Attachment.id)
        .filter(
            AttachmentRelation.entity_type == "record",
            AttachmentRelation.entity_id == str(record_id),
        )
        .order_by(Attachment.created_at.desc())
        .all()
    )
    return [_to_response(a, r) for a, r in rows]
