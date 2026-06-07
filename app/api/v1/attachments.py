from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.entities import Attachment, AttachmentRelation, User
from app.schemas.attachments import (
    AttachmentCreate,
    AttachmentEntidadTipo,
    AttachmentRead,
    AttachmentUpdate,
)
from app.services.access import assert_member_of_project, get_project_id_for_attachment_entity
from app.services.attachments import (
    assert_attachment_read_allowed,
    create_attachment_for_entity,
    delete_attachment,
    ensure_attachment_entidad_exists,
    update_attachment,
)
from app.services.file_storage import (
    attachment_download_path,
    is_stored_attachment,
    read_upload_limited,
    resolve_stored_file,
    save_attachment_file,
)
from app.config import settings

router = APIRouter(prefix="/attachments", tags=["attachments"])


def _load_attachment(attachment_id: UUID, db: Session) -> Attachment | None:
    stmt = (
        select(Attachment)
        .where(Attachment.id == attachment_id)
        .options(selectinload(Attachment.relations))
    )
    return db.scalar(stmt)


@router.get("", response_model=list[AttachmentRead])
def list_attachments(
    entidad_tipo: AttachmentEntidadTipo = Query(...),
    entidad_id: UUID = Query(...),
    viewer_user_id: UUID = Query(
        ...,
        description="Miembro del proyecto que consulta (demo sin JWT)",
    ),
    db: Session = Depends(get_db),
):
    ensure_attachment_entidad_exists(entidad_tipo, entidad_id, db)
    assert_attachment_read_allowed(
        db,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        viewer_user_id=viewer_user_id,
    )
    stmt = (
        select(Attachment)
        .join(AttachmentRelation)
        .where(
            AttachmentRelation.entidad_tipo == entidad_tipo,
            AttachmentRelation.entidad_id == entidad_id,
        )
        .options(selectinload(Attachment.relations))
        .order_by(Attachment.created_at.desc())
    )
    return list(db.scalars(stmt).unique())


@router.post("/upload", response_model=AttachmentRead, status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    uploaded_by: UUID = Form(...),
    entidad_tipo: AttachmentEntidadTipo = Form(...),
    entidad_id: UUID = Form(...),
    db: Session = Depends(get_db),
):
    """Sube un archivo binario y lo vincula a una entidad."""
    content, mime_type = await read_upload_limited(
        file, max_bytes=settings.upload_max_bytes
    )
    nombre_original = file.filename or "archivo"

    attachment_id = uuid4()
    attachment = create_attachment_for_entity(
        db,
        url=attachment_download_path(attachment_id),
        nombre_original=nombre_original,
        mime_type=mime_type,
        tamano_bytes=len(content),
        uploaded_by=uploaded_by,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        attachment_id=attachment_id,
    )
    save_attachment_file(attachment.id, nombre_original, content)
    db.commit()
    db.refresh(attachment)
    loaded = _load_attachment(attachment.id, db)
    if loaded is None:
        raise HTTPException(status_code=500, detail="Error al cargar el adjunto")
    return loaded


@router.post("", response_model=AttachmentRead, status_code=201)
def create_attachment(payload: AttachmentCreate, db: Session = Depends(get_db)):
    """Registra un adjunto por URL externa (sin upload binario)."""
    attachment = create_attachment_for_entity(
        db,
        url=payload.url,
        nombre_original=payload.nombre_original,
        mime_type=payload.mime_type,
        tamano_bytes=payload.tamano_bytes,
        uploaded_by=payload.uploaded_by,
        entidad_tipo=payload.entidad_tipo,
        entidad_id=payload.entidad_id,
    )
    db.commit()
    db.refresh(attachment)
    loaded = _load_attachment(attachment.id, db)
    if loaded is None:
        raise HTTPException(status_code=500, detail="Error al cargar el adjunto")
    return loaded


@router.get("/{attachment_id}/file")
def download_attachment_file(
    attachment_id: UUID,
    viewer_user_id: UUID = Query(
        ...,
        description="Miembro del proyecto que descarga (demo sin JWT)",
    ),
    db: Session = Depends(get_db),
):
    attachment = _load_attachment(attachment_id, db)
    if not attachment:
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    relation = attachment.relations[0] if attachment.relations else None
    if relation is None:
        raise HTTPException(status_code=409, detail="Adjunto sin entidad vinculada")
    project_id = get_project_id_for_attachment_entity(
        db, relation.entidad_tipo, relation.entidad_id
    )
    assert_member_of_project(db, project_id, viewer_user_id)
    if not is_stored_attachment(attachment.url):
        raise HTTPException(
            status_code=404,
            detail="Este adjunto es un enlace externo; no hay archivo local",
        )
    path = resolve_stored_file(attachment.id, attachment.nombre_original)
    if path is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado en almacenamiento")
    return FileResponse(
        path,
        media_type=attachment.mime_type,
        filename=attachment.nombre_original,
    )


@router.get("/{attachment_id}", response_model=AttachmentRead)
def get_attachment(
    attachment_id: UUID,
    viewer_user_id: UUID = Query(
        ...,
        description="Miembro del proyecto que consulta (demo sin JWT)",
    ),
    db: Session = Depends(get_db),
):
    attachment = _load_attachment(attachment_id, db)
    if not attachment:
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    relation = attachment.relations[0] if attachment.relations else None
    if relation is None:
        raise HTTPException(status_code=409, detail="Adjunto sin entidad vinculada")
    assert_attachment_read_allowed(
        db,
        entidad_tipo=relation.entidad_tipo,  # type: ignore[arg-type]
        entidad_id=relation.entidad_id,
        viewer_user_id=viewer_user_id,
    )
    return attachment


@router.patch("/{attachment_id}", response_model=AttachmentRead)
def patch_attachment(
    attachment_id: UUID,
    payload: AttachmentUpdate,
    db: Session = Depends(get_db),
):
    attachment = _load_attachment(attachment_id, db)
    if not attachment:
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    update_attachment(db, attachment, payload)
    db.commit()
    db.refresh(attachment)
    loaded = _load_attachment(attachment.id, db)
    if loaded is None:
        raise HTTPException(status_code=500, detail="Error al cargar el adjunto")
    return loaded


@router.delete("/{attachment_id}", status_code=204)
def remove_attachment(
    attachment_id: UUID,
    actor_user_id: UUID,
    db: Session = Depends(get_db),
):
    attachment = _load_attachment(attachment_id, db)
    if not attachment:
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    actor = db.get(User, actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    delete_attachment(db, attachment, actor_user_id=actor_user_id)
    db.commit()
