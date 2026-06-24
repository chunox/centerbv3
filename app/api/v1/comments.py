"""
API de comentarios — polimórfico: soporta entity_type=record y entity_type=hub_entry.
Rutas bajo /projects/{project_id}/...
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_actor_id
from app.api.v1.projects import get_project_or_404
from app.database import get_db
from app.models.entities import Comment
from app.services.access import require_project_member

router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CommentResponse(BaseModel):
    id: str
    project_id: str
    author_id: str
    entity_type: str
    entity_id: str
    contenido: str
    edited_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateCommentRequest(BaseModel):
    contenido: str


class UpdateCommentRequest(BaseModel):
    contenido: str


def _to_response(c: Comment) -> CommentResponse:
    return CommentResponse(
        id=c.id,
        project_id=c.project_id,
        author_id=c.author_id,
        entity_type=c.entity_type,
        entity_id=c.entity_id,
        contenido=c.contenido,
        edited_at=c.edited_at,
        created_at=c.created_at,
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{project_id}/records/{record_id}/comments", response_model=list[CommentResponse])
def list_record_comments(
    project_id: str,
    record_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    comments = (
        db.query(Comment)
        .filter(
            Comment.project_id == str(project_id),
            Comment.entity_type == "record",
            Comment.entity_id == str(record_id),
        )
        .order_by(Comment.created_at)
        .all()
    )
    return [_to_response(c) for c in comments]


@router.post(
    "/{project_id}/records/{record_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_record_comment(
    project_id: str,
    record_id: str,
    body: CreateCommentRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    comment = Comment(
        project_id=str(project_id),
        author_id=actor_id,
        entity_type="record",
        entity_id=str(record_id),
        contenido=body.contenido,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return _to_response(comment)


@router.patch("/{project_id}/comments/{comment_id}", response_model=CommentResponse)
def update_comment(
    project_id: str,
    comment_id: str,
    body: UpdateCommentRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    comment = db.query(Comment).filter(
        Comment.id == str(comment_id),
        Comment.project_id == str(project_id),
    ).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comentario no encontrado")
    if comment.author_id != actor_id:
        raise HTTPException(status_code=403, detail="Solo el autor puede editar este comentario")
    comment.contenido = body.contenido
    comment.edited_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(comment)
    return _to_response(comment)


@router.delete("/{project_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    project_id: str,
    comment_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    comment = db.query(Comment).filter(
        Comment.id == str(comment_id),
        Comment.project_id == str(project_id),
    ).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comentario no encontrado")
    is_author = comment.author_id == actor_id
    is_pm = ctx.role_slug == "pm"
    if not (is_author or is_pm):
        raise HTTPException(status_code=403, detail="Sin permiso para eliminar este comentario")
    db.delete(comment)
    db.commit()
