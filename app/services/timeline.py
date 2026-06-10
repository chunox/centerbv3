"""Timeline unificado del proyecto — eventos + cronograma (§4.12, §7.1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AuditLog,
    Comment,
    Feature,
    FeatureQuery,
    FeatureReport,
    Milestone,
    Task,
    User,
)
from app.schemas.timeline import (
    ProjectTimelineRead,
    TimelineEventRead,
    TimelinePlanItemRead,
)
from app.services.access import resolve_audit_logs_for_user
from app.services.workflow.visibility import comment_visible_for_capabilities

_ENTIDAD_LABELS = {
    "feature": "Feature",
    "tarea": "Tarea",
    "milestone": "Hito",
    "feature_query": "Consulta",
    "feature_report": "Reporte",
    "document": "Documento",
    "project": "Proyecto",
    "hub_entry": "Publicación",
    "comment": "Comentario",
}


@dataclass
class _EntityMaps:
    milestones: dict[uuid.UUID, Milestone]
    features: dict[uuid.UUID, Feature]
    tasks: dict[uuid.UUID, Task]
    queries: dict[uuid.UUID, FeatureQuery]
    reports: dict[uuid.UUID, FeatureReport]
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
        return m.nombre if m else _ENTIDAD_LABELS.get(entidad_tipo, entidad_tipo)
    if entidad_tipo == "feature":
        f = maps.features.get(entidad_id)
        return f.nombre if f else _ENTIDAD_LABELS.get(entidad_tipo, entidad_tipo)
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
        return entidad_id, m.nombre if m else None, None, None
    if entidad_tipo == "feature":
        f = maps.features.get(entidad_id)
        if not f:
            return None, None, entidad_id, None
        m = maps.milestones.get(f.milestone_id)
        return f.milestone_id, m.nombre if m else None, entidad_id, f.nombre
    if entidad_tipo == "tarea":
        t = maps.tasks.get(entidad_id)
        if not t:
            return None, None, None, None
        f = maps.features.get(t.feature_id)
        m = maps.milestones.get(f.milestone_id) if f else None
        return (
            f.milestone_id if f else None,
            m.nombre if m else None,
            t.feature_id,
            f.nombre if f else None,
        )
    if entidad_tipo == "feature_query":
        q = maps.queries.get(entidad_id)
        if not q:
            return None, None, None, None
        f = maps.features.get(q.feature_id)
        m = maps.milestones.get(f.milestone_id) if f else None
        return (
            f.milestone_id if f else None,
            m.nombre if m else None,
            q.feature_id,
            f.nombre if f else None,
        )
    if entidad_tipo == "feature_report":
        r = maps.reports.get(entidad_id)
        if not r:
            return None, None, None, None
        f = maps.features.get(r.feature_id)
        m = maps.milestones.get(f.milestone_id) if f else None
        return (
            f.milestone_id if f else None,
            m.nombre if m else None,
            r.feature_id,
            f.nombre if f else None,
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
    milestones = {
        m.id: m
        for m in db.scalars(
            select(Milestone).where(Milestone.project_id == project_id)
        )
    }
    features = {
        f.id: f
        for f in db.scalars(
            select(Feature).where(Feature.project_id == project_id)
        )
    }
    tasks = {
        t.id: t
        for t in db.scalars(select(Task).where(Task.project_id == project_id))
    }
    feature_ids = list(features.keys())
    queries: dict[uuid.UUID, FeatureQuery] = {}
    reports: dict[uuid.UUID, FeatureReport] = {}
    if feature_ids:
        queries = {
            q.id: q
            for q in db.scalars(
                select(FeatureQuery).where(FeatureQuery.feature_id.in_(feature_ids))
            )
        }
        reports = {
            r.id: r
            for r in db.scalars(
                select(FeatureReport).where(FeatureReport.feature_id.in_(feature_ids))
            )
        }
    users: dict[uuid.UUID, User] = {}
    return _EntityMaps(
        milestones=milestones,
        features=features,
        tasks=tasks,
        queries=queries,
        reports=reports,
        users=users,
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
            key=lambda m: (m.orden, m.fecha_inicio),
        )
        for milestone in milestone_rows:
            if milestone_id is not None and milestone.id != milestone_id:
                continue
            plan.append(
                TimelinePlanItemRead(
                    id=milestone.id,
                    tipo="milestone",
                    nombre=milestone.nombre,
                    fecha_inicio=milestone.fecha_inicio,
                    fecha_fin=milestone.fecha_fin,
                    estado=milestone.estado,
                    milestone_id=milestone.id,
                    milestone_nombre=milestone.nombre,
                    orden=milestone.orden,
                )
            )
        feature_rows = sorted(
            maps.features.values(),
            key=lambda f: (f.fecha_inicio, f.nombre),
        )
        for feature in feature_rows:
            if feature_id is not None and feature.id != feature_id:
                continue
            if milestone_id is not None and feature.milestone_id != milestone_id:
                continue
            parent = maps.milestones.get(feature.milestone_id)
            plan.append(
                TimelinePlanItemRead(
                    id=feature.id,
                    tipo="feature",
                    nombre=feature.nombre,
                    fecha_inicio=feature.fecha_inicio,
                    fecha_fin=feature.fecha_fin,
                    estado=feature.estado,
                    milestone_id=feature.milestone_id,
                    milestone_nombre=parent.nombre if parent else None,
                    feature_tipo=feature.tipo,
                )
            )

    return ProjectTimelineRead(eventos=eventos, plan=plan)
