from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class MilestoneSyncJobRequest(BaseModel):
    project_id: UUID | None = None


class MilestoneSyncJobResponse(BaseModel):
    milestones_updated: int
