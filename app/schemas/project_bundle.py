from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.audit_logs import AuditLogRead
from app.schemas.feature_queries import FeatureQueryRead
from app.schemas.feature_reports import FeatureReportRead
from app.schemas.features import FeatureRead
from app.schemas.milestones import MilestoneRead
from app.schemas.projects import ProjectRead
from app.schemas.records import RecordRead
from app.schemas.task_dependencies import TaskDependencyRead
from app.schemas.tasks import TaskRead


class BundleFeatureReportRead(FeatureReportRead):
    feature_nombre: str | None = None
    milestone_id: UUID | None = None


class BundleFeatureQueryRead(FeatureQueryRead):
    feature_nombre: str | None = None
    milestone_id: UUID | None = None


class FeatureContextEntryRead(BaseModel):
    milestone_id: UUID = Field(serialization_alias="milestoneId")
    milestone_nombre: str = Field(serialization_alias="milestoneNombre")
    feature: FeatureRead

    model_config = {"populate_by_name": True}


class ProjectBundleRead(BaseModel):
    project: ProjectRead
    record_types: list[str] = Field(default_factory=list, serialization_alias="recordTypes")
    records_by_type: dict[str, list[RecordRead]] = Field(
        default_factory=dict, serialization_alias="recordsByType"
    )
    children_by_parent: dict[str, list[RecordRead]] = Field(
        default_factory=dict, serialization_alias="childrenByParent"
    )
    milestones: list[MilestoneRead]
    features_by_milestone: dict[str, list[FeatureRead]] = Field(
        serialization_alias="featuresByMilestone"
    )
    tasks_by_feature: dict[str, list[TaskRead]] = Field(
        serialization_alias="tasksByFeature"
    )
    feature_context: dict[str, FeatureContextEntryRead] = Field(
        serialization_alias="featureContext"
    )
    reports: list[BundleFeatureReportRead]
    queries: list[BundleFeatureQueryRead]
    audit_logs: list[AuditLogRead] = Field(serialization_alias="auditLogs")
    inbox_action_count: int = Field(serialization_alias="inboxActionCount")
    task_dependencies: list[TaskDependencyRead] = Field(
        serialization_alias="taskDependencies", default_factory=list
    )

    model_config = {"populate_by_name": True}
