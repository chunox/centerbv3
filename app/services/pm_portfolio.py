"""Agregación liviana del portfolio PM (todos los proyectos donde el usuario es PM)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AuditLog,
    Feature,
    FeatureQuery,
    FeatureReport,
    Milestone,
    Project,
    ProjectMember,
)
from app.schemas.pm_portfolio import (
    PmAttentionItemRead,
    PmCriticalMilestoneRead,
    PmHealth,
    PmHealthReason,
    PmInboxBreakdownRead,
    PmPortfolioActivityRead,
    PmPortfolioRead,
    PmPortfolioTotalsRead,
    PmProjectSummaryRead,
)
from app.services.audit_display import audit_log_to_read
from app.services.organizations import get_org_member
from app.services.project_bundle import _PENDING_QUERY_STATES

AT_RISK_DAYS = 14
STALLED_DAYS = 14
ACTIVITY_LIMIT = 10
CRITICAL_MILESTONES_LIMIT = 8

_ACTIVE_MILESTONE_STATES = frozenset({"en_progreso", "en_progreso_con_bug"})
_CRITICAL_MILESTONE_STATES = frozenset(
    {"pendiente", "en_progreso", "en_progreso_con_bug"}
)


def _empty_totals() -> PmPortfolioTotalsRead:
    empty_breakdown = PmInboxBreakdownRead(
        pending_reports=0,
        pending_queries=0,
        pending_releases=0,
    )
    return PmPortfolioTotalsRead(
        active_projects=0,
        inbox_total=0,
        avg_progress_pct=0,
        needs_attention=0,
        at_risk_count=0,
        overdue_count=0,
        blocked_total=0,
        features_pending_total=0,
        inbox_breakdown=empty_breakdown,
    )


def _compute_health(
    *,
    estado: str,
    fecha_fin: date,
    features_blocked: int,
    inbox_action_count: int,
    today: date,
) -> PmHealth:
    if estado in ("cerrado", "cancelado"):
        return "closed"
    if estado == "activo" and fecha_fin < today:
        return "overdue"
    if estado == "activo" and (
        fecha_fin <= today + timedelta(days=AT_RISK_DAYS)
        or features_blocked > 0
        or inbox_action_count > 0
    ):
        return "at_risk"
    return "on_track"


def _health_reasons(
    *,
    estado: str,
    fecha_fin: date,
    features_blocked: int,
    inbox_action_count: int,
    today: date,
) -> list[PmHealthReason]:
    if estado in ("cerrado", "cancelado"):
        return []

    reasons: list[PmHealthReason] = []
    if estado == "activo" and fecha_fin < today:
        reasons.append("fecha_vencida")
    elif estado == "activo" and fecha_fin <= today + timedelta(days=AT_RISK_DAYS):
        reasons.append("fecha_proxima")
    if features_blocked > 0:
        reasons.append("features_bloqueadas")
    if inbox_action_count > 0:
        reasons.append("bandeja_pendiente")
    return reasons


def _deadline_fields(
    *,
    estado: str,
    fecha_fin: date,
    today: date,
) -> tuple[int | None, int]:
    if estado in ("cerrado", "cancelado"):
        return None, 0
    if fecha_fin < today:
        return None, (today - fecha_fin).days
    return (fecha_fin - today).days, 0


def _is_stalled(
    *,
    estado: str,
    last_activity_at: datetime | None,
    project_created_at: datetime,
    today: date,
) -> bool:
    if estado != "activo":
        return False
    reference = last_activity_at or project_created_at
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    ref_date = reference.date()
    return (today - ref_date).days > STALLED_DAYS


def _active_milestone_by_project(
    db: Session,
    project_ids: list[UUID],
) -> dict[UUID, str]:
    milestones = list(
        db.scalars(
            select(Milestone)
            .where(
                Milestone.project_id.in_(project_ids),
                Milestone.estado.in_(_ACTIVE_MILESTONE_STATES),
            )
            .order_by(Milestone.project_id, Milestone.orden)
        )
    )
    result: dict[UUID, str] = {}
    for milestone in milestones:
        if milestone.project_id not in result:
            result[milestone.project_id] = milestone.nombre
    return result


def _last_activity_by_project(
    db: Session,
    project_ids: list[UUID],
) -> dict[UUID, datetime]:
    return dict(
        db.execute(
            select(AuditLog.project_id, func.max(AuditLog.created_at))
            .where(AuditLog.project_id.in_(project_ids))
            .group_by(AuditLog.project_id)
        ).all()
    )


def _build_attention_items(
    db: Session,
    projects: list[Project],
    project_ids: list[UUID],
) -> list[PmAttentionItemRead]:
    project_names = {p.id: p.nombre for p in projects}
    items: list[PmAttentionItemRead] = []

    report_rows = db.execute(
        select(FeatureReport, Feature)
        .join(Feature, FeatureReport.feature_id == Feature.id)
        .where(
            Feature.project_id.in_(project_ids),
            FeatureReport.estado == "pendiente",
        )
    ).all()
    for report, feature in report_rows:
        tipo_label = "Bug" if report.tipo == "bug" else "Mejora"
        items.append(
            PmAttentionItemRead(
                kind="report",
                id=report.id,
                project_id=feature.project_id,
                project_nombre=project_names[feature.project_id],
                title=tipo_label,
                subtitle=feature.nombre,
                report_tipo=report.tipo,
                created_at=report.created_at,
            )
        )

    query_rows = db.execute(
        select(FeatureQuery, Feature)
        .join(Feature, FeatureQuery.feature_id == Feature.id)
        .where(
            Feature.project_id.in_(project_ids),
            FeatureQuery.estado.in_(_PENDING_QUERY_STATES),
        )
    ).all()
    for query, feature in query_rows:
        items.append(
            PmAttentionItemRead(
                kind="query",
                id=query.id,
                project_id=feature.project_id,
                project_nombre=project_names[feature.project_id],
                title=query.titulo,
                subtitle=feature.nombre,
                created_at=query.created_at,
            )
        )

    release_features = list(
        db.scalars(
            select(Feature).where(
                Feature.project_id.in_(project_ids),
                Feature.estado == "esperando_liberacion_pm",
            )
        )
    )
    for feature in release_features:
        items.append(
            PmAttentionItemRead(
                kind="release",
                id=feature.id,
                project_id=feature.project_id,
                project_nombre=project_names[feature.project_id],
                title=feature.nombre,
                subtitle="Esperando liberación PM",
                created_at=feature.updated_at,
            )
        )

    items.sort(key=lambda item: item.created_at, reverse=True)
    return items


def _build_recent_activity(
    db: Session,
    projects: list[Project],
    project_ids: list[UUID],
) -> list[PmPortfolioActivityRead]:
    project_names = {p.id: p.nombre for p in projects}
    logs = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.project_id.in_(project_ids))
            .order_by(AuditLog.created_at.desc())
            .limit(ACTIVITY_LIMIT)
        )
    )
    user_cache: dict[UUID, str | None] = {}
    activity: list[PmPortfolioActivityRead] = []
    for log in logs:
        read = audit_log_to_read(db, log, cache=user_cache)
        activity.append(
            PmPortfolioActivityRead(
                id=read.id,
                project_id=read.project_id,
                project_nombre=project_names[read.project_id],
                user_nombre=read.user_nombre,
                entidad_tipo=read.entidad_tipo,
                entidad_id=read.entidad_id,
                accion=read.accion,
                campo=read.campo,
                valor_anterior=read.valor_anterior,
                valor_nuevo=read.valor_nuevo,
                created_at=read.created_at,
            )
        )
    return activity


def _build_critical_milestones(
    db: Session,
    projects: list[Project],
    project_ids: list[UUID],
    today: date,
) -> list[PmCriticalMilestoneRead]:
    project_names = {p.id: p.nombre for p in projects}
    active_project_ids = [p.id for p in projects if p.estado == "activo"]
    if not active_project_ids:
        return []

    cutoff = today + timedelta(days=AT_RISK_DAYS)
    milestones = list(
        db.scalars(
            select(Milestone)
            .where(
                Milestone.project_id.in_(active_project_ids),
                Milestone.estado.in_(_CRITICAL_MILESTONE_STATES),
                Milestone.fecha_fin <= cutoff,
            )
            .order_by(Milestone.fecha_fin, Milestone.orden)
            .limit(CRITICAL_MILESTONES_LIMIT)
        )
    )
    return [
        PmCriticalMilestoneRead(
            milestone_id=m.id,
            project_id=m.project_id,
            project_nombre=project_names[m.project_id],
            nombre=m.nombre,
            estado=m.estado,
            fecha_fin=m.fecha_fin,
            days_remaining=max(0, (m.fecha_fin - today).days),
        )
        for m in milestones
    ]


def build_pm_portfolio(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
) -> PmPortfolioRead:
    if not get_org_member(db, organization_id, user_id):
        raise HTTPException(status_code=403, detail="No eres miembro de la organización")

    projects = list(
        db.scalars(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(
                Project.organization_id == organization_id,
                ProjectMember.user_id == user_id,
                ProjectMember.rol == "pm",
            )
            .order_by(Project.created_at.desc())
        )
    )

    if not projects:
        return PmPortfolioRead(
            organization_id=organization_id,
            projects=[],
            totals=_empty_totals(),
            attention_items=[],
            recent_activity=[],
            critical_milestones=[],
        )

    project_ids = [p.id for p in projects]
    today = date.today()

    milestone_counts = dict(
        db.execute(
            select(Milestone.project_id, func.count())
            .where(Milestone.project_id.in_(project_ids))
            .group_by(Milestone.project_id)
        ).all()
    )

    feature_rows = db.execute(
        select(
            Feature.project_id,
            func.count()
            .filter(Feature.estado != "cancelado")
            .label("features_total"),
            func.count()
            .filter(Feature.estado == "completado")
            .label("features_completed"),
            func.count()
            .filter(Feature.estado == "en_progreso")
            .label("features_in_progress"),
            func.count()
            .filter(and_(Feature.bloqueada.is_(True), Feature.estado != "cancelado"))
            .label("features_blocked"),
            func.count()
            .filter(Feature.estado == "esperando_liberacion_pm")
            .label("release_count"),
            func.count()
            .filter(Feature.estado == "pendiente")
            .label("features_pending"),
            func.count()
            .filter(Feature.estado == "uat")
            .label("features_uat"),
            func.count()
            .filter(Feature.estado == "esperando_validacion_cliente")
            .label("features_awaiting_client"),
        )
        .where(Feature.project_id.in_(project_ids))
        .group_by(Feature.project_id)
    ).all()
    feature_stats = {row.project_id: row for row in feature_rows}

    report_counts = dict(
        db.execute(
            select(Feature.project_id, func.count())
            .join(FeatureReport, FeatureReport.feature_id == Feature.id)
            .where(
                Feature.project_id.in_(project_ids),
                FeatureReport.estado == "pendiente",
            )
            .group_by(Feature.project_id)
        ).all()
    )

    query_counts = dict(
        db.execute(
            select(Feature.project_id, func.count())
            .join(FeatureQuery, FeatureQuery.feature_id == Feature.id)
            .where(
                Feature.project_id.in_(project_ids),
                FeatureQuery.estado.in_(_PENDING_QUERY_STATES),
            )
            .group_by(Feature.project_id)
        ).all()
    )

    active_milestones = _active_milestone_by_project(db, project_ids)
    last_activity_map = _last_activity_by_project(db, project_ids)

    summaries: list[PmProjectSummaryRead] = []
    for project in projects:
        stats = feature_stats.get(project.id)
        features_total = int(stats.features_total) if stats else 0
        features_completed = int(stats.features_completed) if stats else 0
        features_in_progress = int(stats.features_in_progress) if stats else 0
        features_blocked = int(stats.features_blocked) if stats else 0
        features_pending = int(stats.features_pending) if stats else 0
        features_uat = int(stats.features_uat) if stats else 0
        features_awaiting_client = int(stats.features_awaiting_client) if stats else 0
        release_count = int(stats.release_count) if stats else 0
        pending_reports = report_counts.get(project.id, 0)
        pending_queries = query_counts.get(project.id, 0)
        inbox_action_count = pending_reports + pending_queries + release_count
        progress_pct = (
            round(features_completed / features_total * 100) if features_total else 0
        )
        health = _compute_health(
            estado=project.estado,
            fecha_fin=project.fecha_fin,
            features_blocked=features_blocked,
            inbox_action_count=inbox_action_count,
            today=today,
        )
        days_remaining, days_overdue = _deadline_fields(
            estado=project.estado,
            fecha_fin=project.fecha_fin,
            today=today,
        )
        last_activity_at = last_activity_map.get(project.id)

        summaries.append(
            PmProjectSummaryRead(
                project_id=project.id,
                nombre=project.nombre,
                tipo=project.tipo,
                estado=project.estado,
                fecha_inicio=project.fecha_inicio,
                fecha_fin=project.fecha_fin,
                milestone_count=milestone_counts.get(project.id, 0),
                features_total=features_total,
                features_completed=features_completed,
                features_in_progress=features_in_progress,
                features_blocked=features_blocked,
                features_pending=features_pending,
                features_uat=features_uat,
                features_awaiting_client=features_awaiting_client,
                progress_pct=progress_pct,
                inbox_action_count=inbox_action_count,
                inbox_breakdown=PmInboxBreakdownRead(
                    pending_reports=pending_reports,
                    pending_queries=pending_queries,
                    pending_releases=release_count,
                ),
                health=health,
                days_remaining=days_remaining,
                days_overdue=days_overdue,
                health_reasons=_health_reasons(
                    estado=project.estado,
                    fecha_fin=project.fecha_fin,
                    features_blocked=features_blocked,
                    inbox_action_count=inbox_action_count,
                    today=today,
                ),
                active_milestone_nombre=active_milestones.get(project.id),
                last_activity_at=last_activity_at,
                is_stalled=_is_stalled(
                    estado=project.estado,
                    last_activity_at=last_activity_at,
                    project_created_at=project.created_at,
                    today=today,
                ),
            )
        )

    active_projects = sum(1 for p in projects if p.estado == "activo")
    inbox_total = sum(s.inbox_action_count for s in summaries)
    avg_progress_pct = (
        round(sum(s.progress_pct for s in summaries) / len(summaries))
        if summaries
        else 0
    )
    needs_attention = sum(1 for s in summaries if s.inbox_action_count > 0)
    at_risk_count = sum(1 for s in summaries if s.health == "at_risk")
    overdue_count = sum(1 for s in summaries if s.health == "overdue")
    blocked_total = sum(s.features_blocked for s in summaries)
    features_pending_total = sum(s.features_pending for s in summaries)
    global_breakdown = PmInboxBreakdownRead(
        pending_reports=sum(s.inbox_breakdown.pending_reports for s in summaries),
        pending_queries=sum(s.inbox_breakdown.pending_queries for s in summaries),
        pending_releases=sum(s.inbox_breakdown.pending_releases for s in summaries),
    )

    return PmPortfolioRead(
        organization_id=organization_id,
        projects=summaries,
        totals=PmPortfolioTotalsRead(
            active_projects=active_projects,
            inbox_total=inbox_total,
            avg_progress_pct=avg_progress_pct,
            needs_attention=needs_attention,
            at_risk_count=at_risk_count,
            overdue_count=overdue_count,
            blocked_total=blocked_total,
            features_pending_total=features_pending_total,
            inbox_breakdown=global_breakdown,
        ),
        attention_items=_build_attention_items(db, projects, project_ids),
        recent_activity=_build_recent_activity(db, projects, project_ids),
        critical_milestones=_build_critical_milestones(db, projects, project_ids, today),
    )
