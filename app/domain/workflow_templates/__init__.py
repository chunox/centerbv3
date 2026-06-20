"""Plantillas de workflow por defecto (waterfall + scrum)."""
from app.domain.workflow_templates._common import *  # noqa: F403
from app.domain.workflow_templates.router import workflow_for_template
from app.domain.workflow_templates.scrum import (
    default_feature_workflow_scrum_base,
    default_feature_workflow_scrum_cliente,
    default_feature_workflow_scrum_interno,
    default_product_backlog_workflow,
    default_sprint_workflow,
    default_task_workflow_epic_container,
    default_task_workflow_scrum_dev,
    default_task_workflow_scrum_story_base,
    default_task_workflow_scrum_story_cliente,
    default_task_workflow_scrum_story_interno,
)
from app.domain.workflow_templates.waterfall import (
    default_feature_workflow_con_cliente,
    default_feature_workflow_freestyle,
    default_feature_workflow_interno,
    default_milestone_workflow,
    default_query_workflow,
    default_query_workflow_freestyle,
    default_report_workflow,
    default_report_workflow_freestyle,
    default_task_workflow,
    workflow_for_project_tipo,
)

__all__ = [
    "workflow_for_template",
    "workflow_for_project_tipo",
    "default_feature_workflow_con_cliente",
    "default_feature_workflow_interno",
    "default_feature_workflow_freestyle",
    "default_feature_workflow_scrum_base",
    "default_feature_workflow_scrum_interno",
    "default_feature_workflow_scrum_cliente",
    "default_task_workflow_scrum_story_base",
    "default_task_workflow_scrum_story_interno",
    "default_task_workflow_scrum_story_cliente",
    "default_task_workflow_epic_container",
    "default_task_workflow_scrum_dev",
    "default_task_workflow",
    "default_query_workflow",
    "default_query_workflow_freestyle",
    "default_report_workflow",
    "default_report_workflow_freestyle",
    "default_milestone_workflow",
    "default_sprint_workflow",
    "default_product_backlog_workflow",
]
