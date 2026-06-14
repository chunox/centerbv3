"""Agregación de equipo cross-proyecto para portfolio PM."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectMember, ProjectRole
from app.schemas.portfolio_team_workload import (
    PortfolioTeamProjectRead,
    PortfolioTeamWorkloadRead,
    PortfolioTeamWorkloadTotalsRead,
)
from app.services.organizations import get_org_member
from app.services.team_board import build_team_board


def _pm_projects(db: Session, organization_id: UUID, user_id: UUID) -> list[Project]:
    return list(
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


def build_portfolio_team_workload(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
) -> PortfolioTeamWorkloadRead:
    if not get_org_member(db, organization_id, user_id):
        raise HTTPException(status_code=403, detail="No eres miembro de la organización")

    projects = _pm_projects(db, organization_id, user_id)
    if not projects:
        return PortfolioTeamWorkloadRead(
            organization_id=organization_id,
            projects=[],
            totals=PortfolioTeamWorkloadTotalsRead(),
        )

    project_rows: list[PortfolioTeamProjectRead] = []
    unique_members: set[UUID] = set()
    totals = PortfolioTeamWorkloadTotalsRead(projects=len(projects))

    for project in projects:
        board = build_team_board(db, project, stamp_project=True)
        for member in board.members:
            unique_members.add(member.user_id)
        totals.assignments += board.totals.assignments
        totals.active += board.totals.active
        totals.unassigned += board.totals.unassigned
        project_rows.append(
            PortfolioTeamProjectRead(
                project_id=project.id,
                nombre=project.nombre,
                pack_slug=project.pack_slug or "software",
                members=board.members,
                unassigned=board.unassigned,
                feature_schedules=board.feature_schedules,
                totals=board.totals,
            )
        )

    totals.members = len(unique_members)

    return PortfolioTeamWorkloadRead(
        organization_id=organization_id,
        projects=project_rows,
        totals=totals,
    )
