"""Router de workflows por template/pack."""
from __future__ import annotations

from typing import Any

from app.domain.project_templates import SCRUM_TEMPLATE_SLUGS
from app.domain.workflow_templates import scrum, waterfall
from app.domain.workflow_templates.waterfall import _TEMPLATE_TO_TIPO


def workflow_for_template(template_slug: str, entity_type: str) -> dict[str, Any]:
    """Resuelve el workflow por template_slug."""
    if entity_type == "feature":
        if template_slug == "t6_scrum_interno":
            return scrum.default_feature_workflow_scrum_interno()
        if template_slug == "t7_scrum_cliente":
            return scrum.default_feature_workflow_scrum_cliente()
    if entity_type == "sprint" and template_slug in SCRUM_TEMPLATE_SLUGS:
        return scrum.default_sprint_workflow()
    if entity_type == "product_backlog" and template_slug in SCRUM_TEMPLATE_SLUGS:
        return scrum.default_product_backlog_workflow()
    if entity_type == "task" and template_slug in SCRUM_TEMPLATE_SLUGS:
        return scrum.default_task_workflow_scrum_dev()
    tipo = _TEMPLATE_TO_TIPO.get(template_slug, "interno")
    return waterfall.workflow_for_project_tipo(tipo, entity_type)
