import uuid
from typing import Literal

from sqlalchemy.orm import Session

from app.models.entities import Notification

NotificationTipo = Literal[
    "estado_changed",
    "asignado",
    "mencionado",
    "query_creada",
    "query_pendiente_aprobacion",
    "query_respondida",
    "feature_bloqueada",
    "feature_desbloqueada",
    "reporte_recibido",
    "reporte_resuelto",
]
NotificationEntidadTipo = Literal["feature", "tarea", "feature_query", "feature_report"]


def create_notification(
    db: Session,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    tipo: NotificationTipo,
    entidad_tipo: NotificationEntidadTipo,
    entidad_id: uuid.UUID,
    leida: bool = False,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        project_id=project_id,
        tipo=tipo,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        leida=leida,
    )
    db.add(notification)
    return notification
