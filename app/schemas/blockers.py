from datetime import datetime
from pydantic import BaseModel


class BlockerResponse(BaseModel):
    id: str
    record_id: str
    project_id: str
    description: str
    created_by: str
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_note: str | None = None
    is_resolved: bool

    model_config = {"from_attributes": True}


class CreateBlockerRequest(BaseModel):
    description: str


class ResolveBlockerRequest(BaseModel):
    resolution_note: str | None = None
