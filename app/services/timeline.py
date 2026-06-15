"""Timeline unificado del proyecto — eventos + cronograma (§4.12, §7.1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.entities import AuditLog, Comment, ProjectRecord, User
from app.schemas.timeline import (
    ProjectTimelineRead,
    TimelineEventRead,
    TimelinePlanItemRead,
)
from app.services.access import resolve_audit_logs_for_user
from app.services.records.repository import _data, list_records
from app.services.workflow.visibility import comment_visible_for_capabilities

_ENTIDAD_LABELS = {
    "feature": "Feature",
    "tarea": "Tarea",
    "milestone": "Hito",
    "feature_query": "Consulta",
    "feature_report": "Reporte",
    "project": "Proyecto",
    "hub_entry": "Publicación",
    "comment": "Comentario",
}


@dataclass
class _EntityMaps:
    milestones: dict[uuid.UUID, ProjectRecord]
    features: dict[uuid.UUID, ProjectRecord]
    tasks: dict[uuid.UUID, ProjectRecord]
    queries: dict[uuid.UUID, ProjectRecord]
    reports: dict[uuid.UUID, ProjectRecord]
    users: dict[uuid.UUID, User]


def _user_nombre(users: dict[uuid.UUID, User], user_id: uuid.UUID) -> str:
    user = users.get(user_id)
    return user.nombre if user else "Usuario"


def _entity_label(
    entidad_tipo: str,
    entidad_id: uuid.UUID,
    maps: _EntityMaps,
) -> str:
    if entidad_tipo == "milestone":
        m = maps.milestones.get(entidad_id)
        return m.titulo if m else _ENTIDAD_LABELS.get(entidad_tipo, entidad_tipo)
    if entidad_tipo == "feature":
        f = maps.features.get(entidad_id)
        return f.titulo if f else _ENTIDAD_LABELS.get(entidad_tipo, entidad_tipo)
    if entidad_tipo == "tarea":
        t = maps.tasks.get(entidad_id)
        return t.titulo if t else _ENTIDAD_LABELS.get(entidad_tipo, entidad_tipo)
    if entidad_tipo == "feature_query":
        q = maps.queries.get(entidad_id)
        return q.titulo if q else _ENTIDAD_LABELS.get(entidad_tipo, entidad_tipo)
    if entidad_tipo == "feature_report":
        return _ENTIDAD_LABELS.get(entidad_tipo, entidad_tipo)
    return _ENTIDAD_LABELS.get(entidad_tipo, entidad_tipo)


def _resolve_context(
    entidad_tipo: str,
    entidad_id: uuid.UUID,
    maps: _EntityMaps,
) -> tuple[uuid.UUID | None, str | None, uuid.UUID | None, str | None]:
    if entidad_tipo == "milestone":
        m = maps.milestones.get(entidad_id)
        return entidad_id, m.titulo if m else None, None, None
    if entidad_tipo == "feature":
        f = maps.features.get(entidad_id)
        if not f:
            return None, None, entidad_id, None
        m = maps.milestones.get(f.parent_id) if f.parent_id else None
        return f.parent_id, m.titulo if m else None, entidad_id, f.titulo
    if entidad_tipo == "tarea":
        t = maps.tasks.get(entidad_id)
        if not t:
            return None, None, None, None
        f = maps.features.get(t.parent_id) if t.parent_id else None
        m = maps.milestones.get(f.parent_id) if f and f.parent_id else None
        return (
            f.parent_id if f else None,
            m.titulo if m else None,
            t.parent_id,
            f.titulo if f else None,
        )
    if entidad_tipo == "feature_query":
        q = maps.queries.get(entidad_id)
        if not q:
            return None, None, None, None
        f = maps.features.get(q.parent_id) if q.parent_id else None
        m = maps.milestones.get(f.parent_id) if f and f.parent_id else None
        return (
            f.parent_id if f else None,
            m.titulo if m else None,
            q.parent_id,
            f.titulo if f else None,
        )
    if entidad_tipo == "feature_report":
        r = maps.reports.get(entidad_id)
        if not r:
            return None, None, None, None
        f = maps.features.get(r.parent_id) if r.parent_id else None
        m = maps.milestones.get(f.parent_id) if f and f.parent_id else None
        return (
            f.parent_id if f else None,
            m.titulo if m else None,
            r.parent_id,
            f.titulo if f else None,
        )
    return None, None, None, None


def _matches_scope(
    *,
    milestone_id: uuid.UUID | None,
    feature_id: uuid.UUID | None,
    filter_milestone_id: uuid.UUID | None,
    filter_feature_id: uuid.UUID | None,
) -> bool:
    if filter_feature_id is not None:
        return feature_id == filter_feature_id
    if filter_milestone_id is not None:
        return milestone_id == filter_milestone_id
    return True


def _load_maps(db: Session, project_id: uuid.UUID) -> _EntityMaps:
    all_rows = list_records(db, project_id)
    milestones = {r.id: r for r in all_rows if r.record_type == "milestone"}
    features = {r.id: r for r in all_rows if r.record_type == "feature"}
    tasks = {r.id: r for r in all_rows if r.record_type == "task"}
    queries = {r.id: r for r in all_rows if r.record_type == "query"}
    reports = {r.id: r for r in all_rows if r.record_type == "report"}
    return _EntityMaps(
        milestones=milestones,
        features=features,
        tasks=tasks,
        queries=queries,
        reports=reports,
        users={},
    )


def _comment_filters(maps: _EntityMaps) -> list:
    filters = []
    if maps.features:
        filters.append(
            and_(
                Comment.entidad_tipo == "feature",
                Comment.entidad_id.in_(maps.features.keys()),
            )
        )
    if maps.tasks:
        filters.append(
            and_(
                Comment.entidad_tipo == "tarea",
                Comment.entidad_id.in_(maps.tasks.keys()),
            )
        )
    if maps.queries:
        filters.append(
            and_(
                Comment.entidad_tipo == "feature_query",
                Comment.entidad_id.in_(maps.queries.keys()),
            )
        )
    if maps.reports:
        filters.append(
            and_(
                Comment.entidad_tipo == "feature_report",
                Comment.entidad_id.in_(maps.reports.keys()),
            )
        )
    return filters


def _ensure_users(db: Session, users: dict[uuid.UUID, User], *user_ids: uuid.UUID) -> None:
    missing = [uid for uid in user_ids if uid not in users]
    if not missing:
        return
    for user in db.scalars(select(User).where(User.id.in_(missing))):
        users[user.id] = user


def _comment_visible_to_viewer(
    db: Session,
    project_id: uuid.UUID,
    comment: Comment,
    *,
    viewer_user_id: uuid.UUID | None,
) -> bool:
    return comment_visible_for_capabilities(
        db,
        project_id,
        viewer_user_id=viewer_user_id,
        entidad_tipo=comment.entidad_tipo,
        comment_user_id=comment.user_id,
    )


def build_project_timeline(
    db: Session,
    project_id: uuid.UUID,
    *,
    milestone_id: uuid.UUID | None = None,
    feature_id: uuid.UUID | None = None,
    incluir_eventos: bool = True,
    incluir_plan: bool = True,
    eventos_limit: int = 200,
    eventos_offset: int = 0,
    viewer_user_id: uuid.UUID | None = None,
) -> ProjectTimelineRead:
    maps = _load_maps(db, project_id)
    users = maps.users
    eventos: list[TimelineEventRead] = []

    if incluir_eventos:
        raw_logs = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.project_id == project_id)
                .order_by(AuditLog.created_at.desc())
            )
        )
        logs = resolve_audit_logs_for_user(
            db,
            raw_logs,
            project_id=project_id,
            viewer_user_id=viewer_user_id,
        )
        for log in logs:
            ms_id, ms_nom, ft_id, ft_nom = _resolve_context(
                log.entidad_tipo, log.entidad_id, maps
            )
            if not _matches_scope(
                milestone_id=ms_id,
                feature_id=ft_id,
                filter_milestone_id=milestone_id,
                filter_feature_id=feature_id,
            ):
                continue
            _ensure_users(db, users, log.user_id)
            label = _entity_label(log.entidad_tipo, log.entidad_id, maps)
            eventos.append(
                TimelineEventRead(
                    id=log.id,
                    source="audit",
                    occurred_at=log.created_at,
                    user_id=log.user_id,
                    user_nombre=_user_nombre(users, log.user_id),
                    entidad_tipo=log.entidad_tipo,
                    entidad_id=log.entidad_id,
                    titulo=f"{label} · {log.accion}",
                    accion=log.accion,
                    campo=log.campo,
                    valor_anterior=log.valor_anterior,
                    valor_nuevo=log.valor_nuevo,
                    milestone_id=ms_id,
                    milestone_nombre=ms_nom,
                    feature_id=ft_id,
                    feature_nombre=ft_nom,
                )
            )

        comment_filters = _comment_filters(maps)
        if comment_filters:
            for comment in db.scalars(
                select(Comment)
                .where(or_(*comment_filters))
                .order_by(Comment.created_at.desc())
            ):
                if not _comment_visible_to_viewer(
                    db,
                    project_id,
                    comment,
                    viewer_user_id=viewer_user_id,
                ):
                    continue
                ms_id, ms_nom, ft_id, ft_nom = _resolve_context(
                    comment.entidad_tipo, comment.entidad_id, maps
                )
                if not _matches_scope(
                    milestone_id=ms_id,
                    feature_id=ft_id,
                    filter_milestone_id=milestone_id,
                    filter_feature_id=feature_id,
                ):
                    continue
                _ensure_users(db, users, comment.user_id)
                label = _entity_label(
                    comment.entidad_tipo, comment.entidad_id, maps
                )
                eventos.append(
                    TimelineEventRead(
                        id=comment.id,
                        source="comment",
                        occurred_at=comment.created_at,
                        user_id=comment.user_id,
                        user_nombre=_user_nombre(users, comment.user_id),
                        entidad_tipo=comment.entidad_tipo,
                        entidad_id=comment.entidad_id,
                        titulo=f"Comentario en {label}",
                        contenido=comment.contenido,
                        estado_momento=comment.estado_momento,
                        milestone_id=ms_id,
                        milestone_nombre=ms_nom,
                        feature_id=ft_id,
                        feature_nombre=ft_nom,
                    )
                )

        eventos.sort(key=lambda e: e.occurred_at, reverse=True)
        eventos = eventos[eventos_offset : eventos_offset + eventos_limit]

    plan: list[TimelinePlanItemRead] = []
    if incluir_plan:
        milestone_rows = sorted(
            maps.milestones.values(),
            key=lambda m: (m.orden, m.fecha_inicio or date.min),
        )
        for milestone in milestone_rows:
            if milestone_id is not None and milestone.id != milestone_id:
                continue
            plan.append(
                TimelinePlanItemRead(
                    id=milestone.id,
                    tipo="milestone",
                    nombre=milestone.titulo,
                    fecha_inicio=milestone.fecha_inicio,
                    fecha_fin=milestone.fecha_fin,
                    estado=milestone.estado,
                    milestone_id=milestone.id,
                    milestone_nombre=milestone.titulo,
                    orden=milestone.orden,
                )
            )
        feature_rows = sorted(
            maps.features.values(),
            key=lambda f: (f.fecha_inicio, f.titulo),
        )
        for feature in feature_rows:
            if feature_id is not None and feature.id != feature_id:
                continue
            if milestone_id is not None and feature.parent_id != milestone_id:
                continue
            parent = maps.milestones.get(feature.parent_id) if feature.parent_id else None
            plan.append(
                TimelinePlanItemRead(
                    id=feature.id,
                    tipo="feature",
                    nombre=feature.titulo,
                    fecha_inicio=feature.fecha_inicio,
                    fecha_fin=feature.fecha_fin,
                    estado=feature.estado,
                    milestone_id=feature.parent_id,
                    milestone_nombre=parent.titulo if parent else None,
                    feature_tipo=_data(feature).get("tipo", "desarrollo"),
                )
            )

    return ProjectTimelineRead(eventos=eventos, plan=plan)
