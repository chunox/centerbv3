from pydantic import BaseModel, Field


class ProjectInboxSummaryRead(BaseModel):
    inbox_action_count: int = Field(serialization_alias="inboxActionCount")
    client_inbox_count: int = Field(serialization_alias="clientInboxCount")
    pending_reports: int = Field(serialization_alias="pendingReports")
    pending_queries: int = Field(serialization_alias="pendingQueries")
    pending_releases: int = Field(serialization_alias="pendingReleases")
    pending_validations: int = Field(serialization_alias="pendingValidations")
    counts_by_workbench: dict[str, int] = Field(
        default_factory=dict, serialization_alias="countsByWorkbench"
    )

    model_config = {"populate_by_name": True}
