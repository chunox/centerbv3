"""Resuelve DeliveryService según modo del proyecto."""
from __future__ import annotations

from app.domain.project_mode import delivery_mode_for_project, is_scrum_mode
from app.models.entities import Project
from app.services.delivery.base import DeliveryService
from app.services.delivery.scrum import ScrumRecordService
from app.services.delivery.waterfall import WaterfallRecordService

_WATERFALL = WaterfallRecordService()
_SCRUM = ScrumRecordService()


def get_delivery_service(project: Project) -> DeliveryService:
    if is_scrum_mode(project):
        return _SCRUM
    return _WATERFALL


def delivery_mode_label(project: Project) -> str:
    return delivery_mode_for_project(project).value
