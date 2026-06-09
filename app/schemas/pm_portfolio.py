from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.feature_reports import ReportTipo
from app.schemas.milestones import MilestoneEstado
from app.schemas.projects import ProjectEstado, ProjectTipo

PmHealth = Literal["on_track", "at_risk", "overdue", "closed"]
PmHealthReason = Literal[
    "fecha_vencida",
    "fecha_proxima",
    "features_bloqueadas",
    "bandeja_pendiente",
]
PmAttentionKind = Literal["report", "query", "release"]


class PmInboxBreakdownRead(BaseModel):
    pending_reports: int = Field(serialization_alias="pendingReports")
    pending_queries: int = Field(serialization_alias="pendingQueries")
    pending_releases: int = Field(serialization_alias="pendingReleases")

    model_config = ConfigDict(populate_by_name=True)


class PmProjectSummaryRead(BaseModel):
    project_id: UUID = Field(serialization_alias="projectId")
    nombre: str
    tipo: ProjectTipo
    estado: ProjectEstado
    fecha_inicio: date = Field(serialization_alias="fechaInicio")
    fecha_fin: date = Field(serialization_alias="fechaFin")
    milestone_count: int = Field(serialization_alias="milestoneCount")
    features_total: int = Field(serialization_alias="featuresTotal")
    features_completed: int = Field(serialization_alias="featuresCompleted")
    features_in_progress: int = Field(serialization_alias="featuresInProgress")
    features_blocked: int = Field(serialization_alias="featuresBlocked")
    features_pending: int = Field(serialization_alias="featuresPending")
    features_uat: int = Field(serialization_alias="featuresUat")
    features_awaiting_client: int = Field(serialization_alias="featuresAwaitingClient")
    progress_pct: int = Field(serialization_alias="progressPct")
    inbox_action_count: int = Field(serialization_alias="inboxActionCount")
    inbox_breakdown: PmInboxBreakdownRead = Field(serialization_alias="inboxBreakdown")
    health: PmHealth
    days_remaining: int | None = Field(serialization_alias="daysRemaining")
    days_overdue: int = Field(serialization_alias="daysOverdue")
    health_reasons: list[PmHealthReason] = Field(serialization_alias="healthReasons")
    active_milestone_nombre: str | None = Field(serialization_alias="activeMilestoneNombre")
    last_activity_at: datetime | None = Field(serialization_alias="lastActivityAt")
    is_stalled: bool = Field(serialization_alias="isStalled")

    model_config = ConfigDict(populate_by_name=True)


class PmPortfolioTotalsRead(BaseModel):
    active_projects: int = Field(serialization_alias="activeProjects")
    inbox_total: int = Field(serialization_alias="inboxTotal")
    avg_progress_pct: int = Field(serialization_alias="avgProgressPct")
    needs_attention: int = Field(serialization_alias="needsAttention")
    at_risk_count: int = Field(serialization_alias="atRiskCount")
    overdue_count: int = Field(serialization_alias="overdueCount")
    blocked_total: int = Field(serialization_alias="blockedTotal")
    features_pending_total: int = Field(serialization_alias="featuresPendingTotal")
    inbox_breakdown: PmInboxBreakdownRead = Field(serialization_alias="inboxBreakdown")

    model_config = ConfigDict(populate_by_name=True)


class PmAttentionItemRead(BaseModel):
    kind: PmAttentionKind
    id: UUID
    project_id: UUID = Field(serialization_alias="projectId")
    project_nombre: str = Field(serialization_alias="projectNombre")
    title: str
    subtitle: str | None = None
    report_tipo: ReportTipo | None = Field(default=None, serialization_alias="reportTipo")
    created_at: datetime = Field(serialization_alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class PmPortfolioActivityRead(BaseModel):
    id: UUID
    project_id: UUID = Field(serialization_alias="projectId")
    project_nombre: str = Field(serialization_alias="projectNombre")
    user_nombre: str | None = Field(serialization_alias="userNombre")
    entidad_tipo: str = Field(serialization_alias="entidadTipo")
    entidad_id: UUID = Field(serialization_alias="entidadId")
    accion: str
    campo: str | None = None
    valor_anterior: str | None = Field(serialization_alias="valorAnterior")
    valor_nuevo: str | None = Field(serialization_alias="valorNuevo")
    created_at: datetime = Field(serialization_alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class PmCriticalMilestoneRead(BaseModel):
    milestone_id: UUID = Field(serialization_alias="milestoneId")
    project_id: UUID = Field(serialization_alias="projectId")
    project_nombre: str = Field(serialization_alias="projectNombre")
    nombre: str
    estado: MilestoneEstado
    fecha_fin: date = Field(serialization_alias="fechaFin")
    days_remaining: int = Field(serialization_alias="daysRemaining")

    model_config = ConfigDict(populate_by_name=True)


class PmPortfolioRead(BaseModel):
    organization_id: UUID = Field(serialization_alias="organizationId")
    projects: list[PmProjectSummaryRead]
    totals: PmPortfolioTotalsRead
    attention_items: list[PmAttentionItemRead] = Field(
        default_factory=list,
        serialization_alias="attentionItems",
    )
    recent_activity: list[PmPortfolioActivityRead] = Field(
        default_factory=list,
        serialization_alias="recentActivity",
    )
    critical_milestones: list[PmCriticalMilestoneRead] = Field(
        default_factory=list,
        serialization_alias="criticalMilestones",
    )

    model_config = ConfigDict(populate_by_name=True)
