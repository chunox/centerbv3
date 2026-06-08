import uuid
from datetime import timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    AuditLog,
    Feature,
    FeatureQuery,
    FeatureReport,
    Notification,
    Project,
    Task,
    User,
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
    "comentario_nuevo",
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
    "comentario_nuevo": "Nuevo comentario",
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


def _actor_nombre_for_notification(
    db: Session,
    notification: Notification,
) -> str | None:
    window = timedelta(seconds=10)
    t0 = notification.created_at - window
    t1 = notification.created_at + timedelta(seconds=2)

    if notification.tipo == "reporte_recibido":
        report = db.get(FeatureReport, notification.entidad_id)
        if report:
            user = db.get(User, report.reported_by)
            return user.nombre if user else None

    if notification.tipo in ("mencionado", "comentario_nuevo"):
        log = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.project_id == notification.project_id,
                AuditLog.entidad_tipo == "comment",
                AuditLog.accion == "created",
                AuditLog.user_id != notification.user_id,
                AuditLog.created_at >= t0,
                AuditLog.created_at <= t1,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        if log:
            user = db.get(User, log.user_id)
            return user.nombre if user else None

    log = db.scalar(
        select(AuditLog)
        .where(
            AuditLog.project_id == notification.project_id,
            AuditLog.entidad_tipo == notification.entidad_tipo,
            AuditLog.entidad_id == notification.entidad_id,
            AuditLog.created_at >= t0,
            AuditLog.created_at <= t1,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    if log:
        user = db.get(User, log.user_id)
        return user.nombre if user else None

    if notification.entidad_tipo == "feature_query":
        query = db.get(FeatureQuery, notification.entidad_id)
        if query:
            user = db.get(User, query.created_by)
            return user.nombre if user else None

    return None


def _build_notification_mensaje(
    *,
    tipo: str,
    actor_nombre: str | None,
    entidad_nombre: str | None,
    project_nombre: str | None,
) -> str:
    actor = actor_nombre or "Alguien"
    entity = entidad_nombre or "un elemento"
    project = f" en {project_nombre}" if project_nombre else ""

    mensajes: dict[str, str] = {
        "estado_changed": f"{actor} cambió el estado de la tarea «{entity}»{project}",
        "asignado": f"{actor} te asignó la tarea «{entity}»{project}",
        "mencionado": f"{actor} te mencionó en «{entity}»{project}",
        "query_creada": f"{actor} creó la consulta «{entity}»{project}",
        "query_pendiente_aprobacion": f"{actor} envió la consulta «{entity}» para tu aprobación{project}",
        "query_respondida": f"{actor} respondió la consulta «{entity}»{project}",
        "feature_bloqueada": f"{actor} bloqueó la feature «{entity}»{project}",
        "feature_desbloqueada": f"{actor} desbloqueó la feature «{entity}»{project}",
        "reporte_recibido": f"{actor} envió un reporte sobre «{entity}»{project}",
        "reporte_resuelto": f"{actor} resolvió el reporte «{entity}»{project}",
        "comentario_nuevo": f"{actor} comentó en «{entity}»{project}",
    }
    return mensajes.get(tipo, f"{actor} · {entity}{project}")


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
    actor_nombre = _actor_nombre_for_notification(db, notification)
    mensaje = _build_notification_mensaje(
        tipo=notification.tipo,
        actor_nombre=actor_nombre,
        entidad_nombre=entidad_nombre,
        project_nombre=project_nombre,
    )

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
        "actor_nombre": actor_nombre,
    }
