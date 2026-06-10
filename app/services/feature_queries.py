"""Flujo de consultas (FeatureQuery) — §4.8 INTERACCIONES_APP."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models.entities import Feature, FeatureQuery, Project, ProjectMember
from app.domain.capabilities import (
    QUERY_APPROVE,
    QUERY_CLOSE,
    QUERY_RESPOND,
    QUERY_SEND,
)
from app.services.access import MemberRol, assert_member_has_role, assert_project_active
from app.services.workflow.authorize import assert_capability
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
    "activar_cliente",
    "activar_interno",
    "responder",
    "validar_aceptar",
    "validar_rechazar",
    "cerrar",
    "cerrar_directo",
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
    if tipo == "freestyle":
        return BLOCKING_CON_CLIENTE | BLOCKING_INTERNO
    return BLOCKING_INTERNO


def active_target_for_project(tipo: str) -> str:
    if tipo == "con_cliente":
        return ACTIVE_TARGET_CON_CLIENTE
    if tipo == "freestyle":
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
    from app.domain.capabilities import WORKBENCH_INBOX_DEV, WORKBENCH_INBOX_PM
    from app.services.workflow.capabilities import users_with_capability

    for cap in (WORKBENCH_INBOX_PM, WORKBENCH_INBOX_DEV):
        for member_id in users_with_capability(db, project.id, cap):
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
    from app.domain.capabilities import WORKBENCH_INBOX_PM
    from app.services.workflow.capabilities import users_with_capability

    for pm_id in users_with_capability(db, project.id, WORKBENCH_INBOX_PM):
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
    from app.domain.capabilities import WORKBENCH_INBOX_CLIENT
    from app.services.workflow.capabilities import users_with_capability

    for cliente_id in users_with_capability(db, project.id, WORKBENCH_INBOX_CLIENT):
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


def _apply_query_capability_side_effects(
    db: Session,
    project: Project,
    query: FeatureQuery,
    *,
    action: QueryAction,
    estado_anterior: str,
) -> None:
    if query.estado == estado_anterior:
        return
    if action == "solicitar_envio":
        if project.tipo == "interno":
            _notify_pm(db, project, tipo="query_creada", query_id=query.id)
        else:
            _notify_pm(db, project, tipo="query_pendiente_aprobacion", query_id=query.id)
    elif action == "aprobar_envio":
        if project.tipo in ("con_cliente", "freestyle"):
            _notify_clientes(db, project, query_id=query.id)
        else:
            _notify_pm(db, project, tipo="query_creada", query_id=query.id)
    elif action in ("activar", "activar_cliente"):
        if project.tipo in ("con_cliente", "freestyle"):
            _notify_clientes(db, project, query_id=query.id)
        else:
            _notify_pm(db, project, tipo="query_creada", query_id=query.id)
    elif action == "activar_interno":
        _notify_pm(db, project, tipo="query_creada", query_id=query.id)
    elif action == "responder":
        _notify_query_respondida(db, project, query)
    elif action in ("validar_aceptar", "cerrar", "cerrar_directo"):
        _notify_query_respondida(db, project, query)
    elif action == "validar_rechazar":
        _notify_clientes(db, project, query_id=query.id)
    elif action == "rechazar":
        _notify_query_rechazada(db, project, query)


def apply_query_action(
    db: Session,
    query: FeatureQuery,
    feature: Feature,
    project: Project,
    *,
    action: QueryAction,
    actor_user_id: uuid.UUID,
    form_data: dict | None = None,
) -> FeatureQuery:
    from app.services.workflow.engine import apply_entity_transition

    assert_project_active(project)
    estado_anterior = query.estado

    apply_entity_transition(
        db,
        project,
        query,
        entity_type="query",
        action_id=action,
        actor_user_id=actor_user_id,
        form_data=form_data,
    )
    _apply_query_capability_side_effects(
        db, project, query, action=action, estado_anterior=estado_anterior
    )
    sync_feature_bloqueada(db, feature, project, actor_user_id=actor_user_id)
    return query
