from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.models.entities import Notification, User
from app.schemas.notifications import (
    NotificationCreate,
    NotificationRead,
    NotificationUpdate,
)
from app.services.notifications import (
    NotificationEntidadTipo,
    create_notification,
    notification_display,
)
from app.services.record_validation import AUDIT_RECORD_TYPE, assert_project_record

router = APIRouter(tags=["notifications"])


def _get_user_or_404(user_id: UUID, db: Session) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


def _validate_entidad_in_project(
    entidad_tipo: NotificationEntidadTipo,
    entidad_id: UUID,
    project_id: UUID,
    db: Session,
) -> None:
    record_type = AUDIT_RECORD_TYPE.get(entidad_tipo)
    if record_type is None:
        return
    assert_project_record(
        db,
        record_id=entidad_id,
        project_id=project_id,
        record_type=record_type,
        detail=f"Entidad {entidad_tipo} no encontrada en el proyecto",
    )


@router.get("/{user_id}/notifications", response_model=list[NotificationRead])
def list_notifications(
    user_id: UUID,
    leida: bool | None = Query(default=None),
    project_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _get_user_or_404(user_id, db)
    stmt = select(Notification).where(Notification.user_id == user_id)
    if leida is not None:
        stmt = stmt.where(Notification.leida == leida)
    if project_id is not None:
        stmt = stmt.where(Notification.project_id == project_id)
    stmt = (
        stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
    )
    rows = list(db.scalars(stmt))
    return [notification_display(db, row) for row in rows]


@router.post("/{user_id}/notifications", response_model=NotificationRead, status_code=201)
def create_user_notification(
    user_id: UUID,
    payload: NotificationCreate,
    db: Session = Depends(get_db),
):
    _get_user_or_404(user_id, db)
    get_project_or_404(payload.project_id, db)
    _validate_entidad_in_project(
        payload.entidad_tipo, payload.entidad_id, payload.project_id, db
    )

    notification = create_notification(
        db,
        user_id=user_id,
        project_id=payload.project_id,
        tipo=payload.tipo,
        entidad_tipo=payload.entidad_tipo,
        entidad_id=payload.entidad_id,
    )
    db.commit()
    db.refresh(notification)
    return notification_display(db, notification)


@router.get("/{user_id}/notifications/{notification_id}", response_model=NotificationRead)
def get_notification(
    user_id: UUID, notification_id: UUID, db: Session = Depends(get_db)
):
    _get_user_or_404(user_id, db)
    notification = db.get(Notification, notification_id)
    if not notification or notification.user_id != user_id:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    return notification_display(db, notification)


@router.patch("/{user_id}/notifications/{notification_id}", response_model=NotificationRead)
def update_notification(
    user_id: UUID,
    notification_id: UUID,
    payload: NotificationUpdate,
    db: Session = Depends(get_db),
):
    _get_user_or_404(user_id, db)
    notification = db.get(Notification, notification_id)
    if not notification or notification.user_id != user_id:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")

    notification.leida = payload.leida
    db.commit()
    db.refresh(notification)
    return notification_display(db, notification)
