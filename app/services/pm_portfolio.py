"""Agregación liviana del portfolio PM (todos los proyectos donde el usuario es PM)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AuditLog,
    Project,
    ProjectMember,
    ProjectRecord,
    ProjectRole,
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
from app.services.project_profile import legacy_tipo_for_project
from app.services.organizations import get_org_member
from app.services.records.repository import _data, list_records
from app.services.workflow.categories import (
    batch_load_workflows,
    is_terminal_state,
    state_category,
    state_keys_in_categories,
    state_meta,
)

AT_RISK_DAYS = 14
STALLED_DAYS = 14
ACTIVITY_LIMIT = 10
CRITICAL_MILESTONES_LIMIT = 8

_PM_PENDING_QUERY_CATEGORIES = frozenset({"inbox_pm", "draft", "active"})
_PENDING_QUERY_STATES = frozenset(
    {"borrador", "pendiente_aprobacion_pm", "esperando_pm", "respuesta_cliente"}
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


def _is_feature_cancelled(wf: dict, estado: str) -> bool:
    if estado == "cancelado":
        return True
    return is_terminal_state(wf, estado) and estado == "cancelado"


def _feature_bucket(wf: dict, estado: str, bloqueada: bool) -> str | None:
    if _is_feature_cancelled(wf, estado):
        return None
    cat = state_category(wf, estado)
    if cat == "terminal":
        return "completed"
    if cat == "active":
        return "in_progress"
    if cat == "pending":
        return "pending"
    if cat == "uat":
        return "uat"
    if cat == "inbox_client":
        return "awaiting_client"
    if cat == "inbox_pm":
        return "release"
    if bloqueada:
        return "blocked_marker"
    if estado == "completado":
        return "completed"
    if estado == "en_progreso":
        return "in_progress"
    if estado == "pendiente":
        return "pending"
    if estado == "uat":
        return "uat"
    if estado == "esperando_validacion_cliente":
        return "awaiting_client"
    if estado == "esperando_liberacion_pm":
        return "release"
    return "other"


def _is_pm_pending_report(wf: dict, estado: str) -> bool:
    cat = state_category(wf, estado)
    if cat:
        return cat == "inbox_pm"
    return estado == "pendiente"


def _is_pm_pending_query(wf: dict, estado: str) -> bool:
    if is_terminal_state(wf, estado):
        return False
    cat = state_category(wf, estado)
    if cat:
        return cat in _PM_PENDING_QUERY_CATEGORIES
    return estado in _PENDING_QUERY_STATES


def _records_by_project(
    db: Session, project_ids: list[UUID]
) -> dict[UUID, list[ProjectRecord]]:
    grouped: dict[UUID, list[ProjectRecord]] = defaultdict(list)
    for project_id in project_ids:
        for row in list_records(db, project_id):
            grouped[project_id].append(row)
    return grouped


def _aggregate_feature_stats(
    records_by_project: dict[UUID, list[ProjectRecord]],
    workflows: dict,
) -> dict[UUID, dict[str, int]]:
    stats: dict[UUID, dict[str, int]] = defaultdict(
        lambda: {
            "features_total": 0,
            "features_completed": 0,
            "features_in_progress": 0,
            "features_blocked": 0,
            "release_count": 0,
            "features_pending": 0,
            "features_uat": 0,
            "features_awaiting_client": 0,
        }
    )
    for project_id, rows in records_by_project.items():
        for feature in (r for r in rows if r.record_type == "feature"):
            wf = workflows.get((project_id, "feature"), {})
            bloqueada = bool(_data(feature).get("bloqueada", False))
            bucket = _feature_bucket(wf, feature.estado, bloqueada)
            if bucket is None:
                continue
            row = stats[project_id]
            row["features_total"] += 1
            if bloqueada:
                row["features_blocked"] += 1
            if bucket == "completed":
                row["features_completed"] += 1
            elif bucket == "in_progress":
                row["features_in_progress"] += 1
            elif bucket == "pending":
                row["features_pending"] += 1
            elif bucket == "uat":
                row["features_uat"] += 1
            elif bucket == "awaiting_client":
                row["features_awaiting_client"] += 1
            elif bucket == "release":
                row["release_count"] += 1
    return stats


def _count_reports_by_project(
    records_by_project: dict[UUID, list[ProjectRecord]],
    workflows: dict,
) -> dict[UUID, int]:
    counts: dict[UUID, int] = defaultdict(int)
    for project_id, rows in records_by_project.items():
        wf = workflows.get((project_id, "report"), {})
        for report in (r for r in rows if r.record_type == "report"):
            if _is_pm_pending_report(wf, report.estado):
                counts[project_id] += 1
    return counts


def _count_queries_by_project(
    records_by_project: dict[UUID, list[ProjectRecord]],
    workflows: dict,
) -> dict[UUID, int]:
    counts: dict[UUID, int] = defaultdict(int)
    for project_id, rows in records_by_project.items():
        wf = workflows.get((project_id, "query"), {})
        for query in (r for r in rows if r.record_type == "query"):
            if _is_pm_pending_query(wf, query.estado):
                counts[project_id] += 1
    return counts


def _active_milestone_by_project(
    records_by_project: dict[UUID, list[ProjectRecord]],
    workflows: dict,
) -> dict[UUID, str]:
    result: dict[UUID, str] = {}
    for project_id, rows in records_by_project.items():
        milestones = sorted(
            (r for r in rows if r.record_type == "milestone"),
            key=lambda m: m.orden,
        )
        wf = workflows.get((project_id, "milestone"), {})
        active_keys = state_keys_in_categories(wf, {"active"})
        if not active_keys:
            active_keys = frozenset({"en_progreso", "en_progreso_con_bug"})
        for milestone in milestones:
            if milestone.estado in active_keys:
                result[project_id] = milestone.titulo
                break
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


def _feature_lookup(
    records_by_project: dict[UUID, list[ProjectRecord]],
) -> dict[UUID, ProjectRecord]:
    return {
        row.id: row
        for rows in records_by_project.values()
        for row in rows
        if row.record_type == "feature"
    }


def _build_attention_items(
    projects: list[Project],
    records_by_project: dict[UUID, list[ProjectRecord]],
    workflows: dict,
) -> list[PmAttentionItemRead]:
    project_names = {p.id: p.nombre for p in projects}
    feature_by_id = _feature_lookup(records_by_project)
    items: list[PmAttentionItemRead] = []

    for project_id, rows in records_by_project.items():
        for report in (r for r in rows if r.record_type == "report"):
            wf = workflows.get((project_id, "report"), {})
            if not _is_pm_pending_report(wf, report.estado):
                continue
            feature = feature_by_id.get(report.parent_id) if report.parent_id else None
            tipo = _data(report).get("tipo", "bug")
            tipo_label = "Bug" if tipo == "bug" else "Mejora"
            items.append(
                PmAttentionItemRead(
                    kind="report",
                    id=report.id,
                    project_id=project_id,
                    project_nombre=project_names[project_id],
                    title=tipo_label,
                    subtitle=feature.titulo if feature else "",
                    report_tipo=tipo,
                    created_at=report.created_at,
                )
            )

        for query in (r for r in rows if r.record_type == "query"):
            wf = workflows.get((project_id, "query"), {})
            if not _is_pm_pending_query(wf, query.estado):
                continue
            feature = feature_by_id.get(query.parent_id) if query.parent_id else None
            items.append(
                PmAttentionItemRead(
                    kind="query",
                    id=query.id,
                    project_id=project_id,
                    project_nombre=project_names[project_id],
                    title=query.titulo,
                    subtitle=feature.titulo if feature else "",
                    created_at=query.created_at,
                )
            )

        for feature in (r for r in rows if r.record_type == "feature"):
            wf = workflows.get((project_id, "feature"), {})
            bloqueada = bool(_data(feature).get("bloqueada", False))
            if _feature_bucket(wf, feature.estado, bloqueada) != "release":
                continue
            items.append(
                PmAttentionItemRead(
                    kind="release",
                    id=feature.id,
                    project_id=project_id,
                    project_nombre=project_names[project_id],
                    title=feature.titulo,
                    subtitle="Espera PM",
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
    projects: list[Project],
    records_by_project: dict[UUID, list[ProjectRecord]],
    workflows: dict,
    today: date,
) -> list[PmCriticalMilestoneRead]:
    project_names = {p.id: p.nombre for p in projects}
    active_project_ids = [p.id for p in projects if p.estado == "activo"]
    if not active_project_ids:
        return []

    cutoff = today + timedelta(days=AT_RISK_DAYS)
    candidates: list[tuple[date, int, PmCriticalMilestoneRead]] = []

    for project_id in active_project_ids:
        wf = workflows.get((project_id, "milestone"), {})
        critical_keys = state_keys_in_categories(wf, {"pending", "active"})
        if not critical_keys:
            critical_keys = frozenset({"pendiente", "en_progreso", "en_progreso_con_bug"})
        for milestone in records_by_project.get(project_id, []):
            if milestone.record_type != "milestone":
                continue
            if milestone.fecha_fin is None or milestone.fecha_fin > cutoff:
                continue
            if milestone.estado not in critical_keys:
                continue
            meta = state_meta(wf, milestone.estado)
            candidates.append(
                (
                    milestone.fecha_fin,
                    milestone.orden,
                    PmCriticalMilestoneRead(
                        milestone_id=milestone.id,
                        project_id=project_id,
                        project_nombre=project_names[project_id],
                        nombre=milestone.titulo,
                        estado=milestone.estado,
                        estado_label=meta["label"],
                        estado_badge=meta["badge"],
                        fecha_fin=milestone.fecha_fin,
                        days_remaining=max(0, (milestone.fecha_fin - today).days),
                    ),
                )
            )

    candidates.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in candidates[:CRITICAL_MILESTONES_LIMIT]]


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
            .join(ProjectRole, ProjectRole.id == ProjectMember.role_id)
            .where(
                Project.organization_id == organization_id,
                ProjectMember.user_id == user_id,
                ProjectRole.slug == "pm",
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
    workflows = batch_load_workflows(db, projects)
    records_by_project = _records_by_project(db, project_ids)

    milestone_counts = {
        pid: sum(1 for r in rows if r.record_type == "milestone")
        for pid, rows in records_by_project.items()
    }

    feature_stats = _aggregate_feature_stats(records_by_project, workflows)
    report_counts = _count_reports_by_project(records_by_project, workflows)
    query_counts = _count_queries_by_project(records_by_project, workflows)
    active_milestones = _active_milestone_by_project(records_by_project, workflows)
    last_activity_map = _last_activity_by_project(db, project_ids)

    summaries: list[PmProjectSummaryRead] = []
    for project in projects:
        stats = feature_stats.get(project.id, {})
        features_total = stats.get("features_total", 0)
        features_completed = stats.get("features_completed", 0)
        features_in_progress = stats.get("features_in_progress", 0)
        features_blocked = stats.get("features_blocked", 0)
        features_pending = stats.get("features_pending", 0)
        features_uat = stats.get("features_uat", 0)
        features_awaiting_client = stats.get("features_awaiting_client", 0)
        release_count = stats.get("release_count", 0)
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
                profile_slug=getattr(project, "profile_slug", None) or "default",
                pack_slug=project.pack_slug or "software",
                tipo=legacy_tipo_for_project(project),
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
        attention_items=_build_attention_items(projects, records_by_project, workflows),
        recent_activity=_build_recent_activity(db, projects, project_ids),
        critical_milestones=_build_critical_milestones(
            projects, records_by_project, workflows, today
        ),
    )
