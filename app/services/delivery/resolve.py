"""Resuelve DeliveryService según modo del proyecto."""
from __future__ import annotations

from app.domain.project_mode import delivery_mode_for_project, is_scrum_mode
from app.domain.project_templates import is_scrum_template_slug
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


def resolve_effective_pack_slug(pack_slug: str, template_slug: str | None) -> str:
    """Resuelve alias legacy `software` al pack concreto por plantilla."""
    if pack_slug != "software":
        return pack_slug
    if is_scrum_template_slug(template_slug):
        return "software-scrum"
    return "software-waterfall"


def delivery_mode_label(project: Project) -> str:
    return delivery_mode_for_project(project).value
