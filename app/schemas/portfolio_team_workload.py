"""Schemas para carga de equipo cross-proyecto en portfolio PM."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.team_board import (
    TeamAssignmentRead,
    TeamBoardTotalsRead,
    TeamFeatureScheduleRead,
    TeamMemberBoardRead,
)


class PortfolioTeamProjectRead(BaseModel):
    project_id: UUID = Field(serialization_alias="projectId")
    nombre: str
    pack_slug: str = Field(serialization_alias="packSlug", default="software")
    members: list[TeamMemberBoardRead] = Field(default_factory=list)
    unassigned: list[TeamAssignmentRead] = Field(default_factory=list)
    feature_schedules: list[TeamFeatureScheduleRead] = Field(default_factory=list)
    totals: TeamBoardTotalsRead = Field(default_factory=TeamBoardTotalsRead)

    model_config = ConfigDict(populate_by_name=True)


class PortfolioTeamWorkloadTotalsRead(BaseModel):
    projects: int = 0
    members: int = 0
    assignments: int = 0
    active: int = 0
    unassigned: int = 0

    model_config = ConfigDict(populate_by_name=True)


class PortfolioTeamWorkloadRead(BaseModel):
    organization_id: UUID = Field(serialization_alias="organizationId")
    projects: list[PortfolioTeamProjectRead] = Field(default_factory=list)
    totals: PortfolioTeamWorkloadTotalsRead = Field(
        default_factory=PortfolioTeamWorkloadTotalsRead
    )

    model_config = ConfigDict(populate_by_name=True)
