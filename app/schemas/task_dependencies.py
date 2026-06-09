from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TaskDependencyCreate(BaseModel):
    depends_on_task_id: UUID
    actor_user_id: UUID


class TaskDependencyDelete(BaseModel):
    actor_user_id: UUID


class TaskDependencyRead(BaseModel):
    id: UUID
    project_id: UUID
    task_id: UUID
    depends_on_task_id: UUID
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
