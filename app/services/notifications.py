import uuid
from typing import Literal

from sqlalchemy.orm import Session

from app.models.entities import (
    Feature,
    FeatureQuery,
    FeatureReport,
    Notification,
    Project,
    Task,
)

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


TITULO_POR_TIPO: dict[str, str] = {
    "estado_changed": "Cambio de estado",
    "asignado": "Tarea asignada",
    "mencionado": "Mención en comentario",
    "query_creada": "Nueva consulta",
    "query_pendiente_aprobacion": "Consulta pendiente de aprobación",
    "query_respondida": "Consulta respondida",
    "feature_bloqueada": "Feature bloqueada",
    "feature_desbloqueada": "Feature desbloqueada",
    "reporte_recibido": "Nuevo reporte",
    "reporte_resuelto": "Reporte resuelto",
}


def _entity_display_name(
    db: Session,
    entidad_tipo: str,
    entidad_id: uuid.UUID,
) -> str | None:
    if entidad_tipo == "feature":
        row = db.get(Feature, entidad_id)
        return row.nombre if row else None
    if entidad_tipo == "tarea":
        row = db.get(Task, entidad_id)
        return row.titulo if row else None
    if entidad_tipo == "feature_query":
        row = db.get(FeatureQuery, entidad_id)
        return row.titulo if row else None
    if entidad_tipo == "feature_report":
        row = db.get(FeatureReport, entidad_id)
        if not row:
            return None
        feature = db.get(Feature, row.feature_id)
        feature_name = feature.nombre if feature else "feature"
        return f"{row.tipo} · {feature_name}"
    return None


def notification_display(
    db: Session,
    notification: Notification,
) -> dict:
    project = db.get(Project, notification.project_id)
    entidad_nombre = _entity_display_name(
        db, notification.entidad_tipo, notification.entidad_id
    )
    titulo = TITULO_POR_TIPO.get(notification.tipo, notification.tipo)
    project_nombre = project.nombre if project else None

    mensaje_parts: list[str] = []
    if entidad_nombre:
        mensaje_parts.append(entidad_nombre)
    if project_nombre:
        mensaje_parts.append(project_nombre)
    mensaje = " · ".join(mensaje_parts) if mensaje_parts else titulo

    return {
        "id": notification.id,
        "user_id": notification.user_id,
        "project_id": notification.project_id,
        "tipo": notification.tipo,
        "entidad_tipo": notification.entidad_tipo,
        "entidad_id": notification.entidad_id,
        "leida": notification.leida,
        "created_at": notification.created_at,
        "titulo": titulo,
        "mensaje": mensaje,
        "entidad_nombre": entidad_nombre,
        "project_nombre": project_nombre,
    }
