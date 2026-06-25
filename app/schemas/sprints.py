"""Schemas para operaciones de sprint (Scrum)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class AssignEpicSprintBody(BaseModel):
    epic_ids: list[str]
    sprint_id: str | None
    on_unassign_stories: Literal["abort_if_pending", "return", "cancel"] | None = None
    on_unassign_children: Literal["unchanged", "return_to_backlog", "cancel"] | None = None


class UnassignEpicsPreviewBody(BaseModel):
    epic_ids: list[str]


class AffectedChildPreview(BaseModel):
    id: str
    title: str
    status: str
    scrum_role: str


class AffectedStoryPreview(BaseModel):
    id: str
    title: str
    status: str
    sprint_id: str
    epic_id: str
    is_blocked: bool
    children: list[AffectedChildPreview]


class UnassignEpicsPreviewResponse(BaseModel):
    epic_ids: list[str]
    stories: list[AffectedStoryPreview]
    has_blocked_stories: bool
    requires_confirmation: bool
