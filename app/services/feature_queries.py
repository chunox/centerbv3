"""Flujo de consultas (FeatureQuery) — §4.8 INTERACCIONES_APP."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models.entities import Feature, FeatureQuery, Project, ProjectMember
from app.services.access import (
    MemberRol,
    assert_member_has_role,
    assert_project_active,
)
from app.services.audit import record_audit_log
from app.services.notifications import NotificationTipo, create_notification

QueryEstado = Literal[
    "borrador",
    "pendiente_aprobacion_pm",
    "esperando_cliente",
    "respuesta_cliente",
    "esperando_pm",
    "cerrada",
    "rechazada",
]

QueryAction = Literal[
    "solicitar_envio",
    "aprobar_envio",
    "activar",
    "responder",
    "validar_aceptar",
    "validar_rechazar",
    "cerrar",
    "rechazar",
]

BLOCKING_CON_CLIENTE: frozenset[str] = frozenset(
    {"pendiente_aprobacion_pm", "esperando_cliente", "respuesta_cliente"}
)
BLOCKING_INTERNO: frozenset[str] = frozenset({"esperando_pm"})

ACTIVE_TARGET_CON_CLIENTE = "esperando_cliente"
ACTIVE_TARGET_INTERNO = "esperando_pm"


def blocking_states_for_project(tipo: str) -> frozenset[str]:
    if tipo == "con_cliente":
        return BLOCKING_CON_CLIENTE
    return BLOCKING_INTERNO


def active_target_for_project(tipo: str) -> str:
    if tipo == "con_cliente":
        return ACTIVE_TARGET_CON_CLIENTE
    return ACTIVE_TARGET_INTERNO


def sync_feature_bloqueada(
    db: Session,
    feature: Feature,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> bool:
    """Recalcula features.bloqueada (acumulativo). Devuelve el nuevo valor."""
    db.flush()
    blocking = blocking_states_for_project(project.tipo)
    blocked = bool(
        db.scalar(
            select(
                exists().where(
                    FeatureQuery.feature_id == feature.id,
                    FeatureQuery.estado.in_(blocking),
                )
            )
        )
    )
    previous = feature.bloqueada
    if previous == blocked:
        return blocked

    feature.bloqueada = blocked
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="feature",
        entidad_id=feature.id,
        accion="desbloqueada" if not blocked else "bloqueada",
        campo="bloqueada",
        valor_anterior=str(previous),
        valor_nuevo=str(blocked),
    )
    notif_tipo = "feature_desbloqueada" if not blocked else "feature_bloqueada"
    for rol in ("pm", "dev"):
        members = db.scalars(
            select(ProjectMember.user_id).where(
                ProjectMember.project_id == project.id,
                ProjectMember.rol == rol,
            )
        )
        for member_id in members:
            create_notification(
                db,
                user_id=member_id,
                project_id=project.id,
                tipo=notif_tipo,
                entidad_tipo="feature",
                entidad_id=feature.id,
            )
    return blocked


def _notify_pm(
    db: Session,
    project: Project,
    *,
    tipo: NotificationTipo,
    query_id: uuid.UUID,
) -> None:
    pm_ids = db.scalars(
        select(ProjectMember.user_id).where(
            ProjectMember.project_id == project.id,
            ProjectMember.rol == "pm",
        )
    )
    for pm_id in pm_ids:
        create_notification(
            db,
            user_id=pm_id,
            project_id=project.id,
            tipo=tipo,
            entidad_tipo="feature_query",
            entidad_id=query_id,
        )


def _notify_clientes(
    db: Session,
    project: Project,
    *,
    query_id: uuid.UUID,
) -> None:
    cliente_ids = db.scalars(
        select(ProjectMember.user_id).where(
            ProjectMember.project_id == project.id,
            ProjectMember.rol == "cliente",
        )
    )
    for cliente_id in cliente_ids:
        create_notification(
            db,
            user_id=cliente_id,
            project_id=project.id,
            tipo="query_creada",
            entidad_tipo="feature_query",
            entidad_id=query_id,
        )


def _notify_query_respondida(
    db: Session,
    project: Project,
    query: FeatureQuery,
) -> None:
    """PM y autor de la consulta (§4.13)."""
    _notify_pm(db, project, tipo="query_respondida", query_id=query.id)
    create_notification(
        db,
        user_id=query.created_by,
        project_id=project.id,
        tipo="query_respondida",
        entidad_tipo="feature_query",
        entidad_id=query.id,
    )


def _notify_query_rechazada(
    db: Session,
    project: Project,
    query: FeatureQuery,
) -> None:
    """Autor de la consulta cuando el PM rechaza (§4.13)."""
    create_notification(
        db,
        user_id=query.created_by,
        project_id=project.id,
        tipo="query_rechazada",
        entidad_tipo="feature_query",
        entidad_id=query.id,
    )


def apply_query_action(
    db: Session,
    query: FeatureQuery,
    feature: Feature,
    project: Project,
    *,
    action: QueryAction,
    actor_user_id: uuid.UUID,
    actor_rol: MemberRol,
) -> FeatureQuery:
    assert_project_active(project)
    estado_anterior = query.estado
    target = active_target_for_project(project.tipo)

    if action == "solicitar_envio":
        assert_member_has_role(db, project.id, actor_user_id, actor_rol)
        if actor_rol not in ("dev", "qa"):
            raise HTTPException(
                status_code=403,
                detail="Solo Dev o QA pueden solicitar envío de consulta",
            )
        if query.estado != "borrador":
            raise HTTPException(
                status_code=409,
                detail="Solo consultas en borrador pueden solicitarse para envío",
            )
        if project.tipo == "interno":
            query.estado = "esperando_pm"
            _notify_pm(
                db,
                project,
                tipo="query_creada",
                query_id=query.id,
            )
        else:
            query.estado = "pendiente_aprobacion_pm"
            _notify_pm(
                db,
                project,
                tipo="query_pendiente_aprobacion",
                query_id=query.id,
            )

    elif action == "aprobar_envio":
        assert_member_has_role(db, project.id, actor_user_id, "pm")
        if query.estado != "pendiente_aprobacion_pm":
            raise HTTPException(
                status_code=409,
                detail="Solo consultas pendientes de aprobación PM pueden aprobarse",
            )
        query.estado = target
        if project.tipo == "con_cliente":
            _notify_clientes(db, project, query_id=query.id)
        else:
            _notify_pm(db, project, tipo="query_creada", query_id=query.id)

    elif action == "activar":
        assert_member_has_role(db, project.id, actor_user_id, "pm")
        if query.estado != "borrador":
            raise HTTPException(
                status_code=409,
                detail="Solo consultas en borrador pueden activarse directamente",
            )
        query.estado = target
        if project.tipo == "con_cliente":
            _notify_clientes(db, project, query_id=query.id)
        else:
            _notify_pm(db, project, tipo="query_creada", query_id=query.id)

    elif action == "responder":
        if project.tipo != "con_cliente":
            raise HTTPException(
                status_code=400,
                detail="Responder consulta solo aplica a proyectos con_cliente",
            )
        assert_member_has_role(db, project.id, actor_user_id, "cliente")
        if query.estado != "esperando_cliente":
            raise HTTPException(
                status_code=409,
                detail="La consulta no está esperando respuesta del cliente",
            )
        query.estado = "respuesta_cliente"
        _notify_query_respondida(db, project, query)

    elif action == "validar_aceptar":
        assert_member_has_role(db, project.id, actor_user_id, "pm")
        if project.tipo != "con_cliente":
            raise HTTPException(status_code=400, detail="Acción solo para con_cliente")
        if query.estado != "respuesta_cliente":
            raise HTTPException(
                status_code=409,
                detail="No hay respuesta del cliente pendiente de validación",
            )
        query.estado = "cerrada"
        _notify_query_respondida(db, project, query)

    elif action == "validar_rechazar":
        assert_member_has_role(db, project.id, actor_user_id, "pm")
        if project.tipo != "con_cliente":
            raise HTTPException(status_code=400, detail="Acción solo para con_cliente")
        if query.estado != "respuesta_cliente":
            raise HTTPException(
                status_code=409,
                detail="No hay respuesta del cliente pendiente de validación",
            )
        query.estado = "esperando_cliente"
        _notify_clientes(db, project, query_id=query.id)

    elif action == "cerrar":
        assert_member_has_role(db, project.id, actor_user_id, "pm")
        if project.tipo != "interno":
            raise HTTPException(
                status_code=400,
                detail="Cerrar consulta con esta acción solo aplica a proyectos interno",
            )
        if query.estado != "esperando_pm":
            raise HTTPException(
                status_code=409,
                detail="La consulta no está en esperando_pm",
            )
        query.estado = "cerrada"
        _notify_query_respondida(db, project, query)

    elif action == "rechazar":
        assert_member_has_role(db, project.id, actor_user_id, "pm")
        if query.estado in ("borrador", "cerrada", "rechazada"):
            raise HTTPException(
                status_code=409,
                detail="No se puede rechazar una consulta en este estado",
            )
        query.estado = "rechazada"
        _notify_query_rechazada(db, project, query)

    else:
        raise HTTPException(status_code=400, detail="Acción no reconocida")

    if query.estado != estado_anterior:
        record_audit_log(
            db,
            project_id=project.id,
            user_id=actor_user_id,
            entidad_tipo="feature_query",
            entidad_id=query.id,
            accion="estado_changed",
            campo="estado",
            valor_anterior=estado_anterior,
            valor_nuevo=query.estado,
        )

    db.flush()
    sync_feature_bloqueada(db, feature, project, actor_user_id=actor_user_id)
    return query
