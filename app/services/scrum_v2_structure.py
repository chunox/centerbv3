"""Scrum v2: sprint raíz, épicas e historias como tasks (scrum_role)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Project,
    ProjectBlock,
    ProjectFieldDefinition,
    ProjectRecord,
    ProjectRecordType,
    ProjectRole,
    ProjectRoleCapability,
)

SCRUM_TEMPLATE_SLUGS = frozenset({"t6_scrum_interno", "t7_scrum_cliente"})

SCRUM_ROLE_EPIC = "epic"
SCRUM_ROLE_STORY = "story"
SCRUM_ROLE_DEV = "dev"

MILESTONE_TIPO_BACKLOG = "product_backlog"
MILESTONE_TIPO_SPRINT = "sprint"
MILESTONE_TIPO_SPRINT_LEGACY = "entrega"

BACKLOG_MILESTONE_TITLE = "Product Backlog"


def is_scrum_template(template_slug: str | None) -> bool:
    return template_slug in SCRUM_TEMPLATE_SLUGS


def get_scrum_role(record: ProjectRecord) -> str | None:
    data = record.data if isinstance(record.data, dict) else {}
    role = data.get("scrum_role")
    return str(role) if role in (SCRUM_ROLE_EPIC, SCRUM_ROLE_STORY, SCRUM_ROLE_DEV) else None


def is_scrum_story(record: ProjectRecord) -> bool:
    return record.record_type == "task" and get_scrum_role(record) == SCRUM_ROLE_STORY


def is_scrum_epic_task(record: ProjectRecord) -> bool:
    return record.record_type == "task" and get_scrum_role(record) == SCRUM_ROLE_EPIC


def is_scrum_dev_task(record: ProjectRecord) -> bool:
    return record.record_type == "task" and get_scrum_role(record) == SCRUM_ROLE_DEV


def get_epic_task_id(record: ProjectRecord) -> uuid.UUID | None:
    data = record.data if isinstance(record.data, dict) else {}
    raw = data.get("epic_task_id") or data.get("parent_task_id")
    if raw is None or raw == "":
        return None
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return None


def get_story_task_id(record: ProjectRecord) -> uuid.UUID | None:
    data = record.data if isinstance(record.data, dict) else {}
    raw = data.get("parent_task_id")
    if raw is None or raw == "":
        return None
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return None


def milestone_tipo(milestone: ProjectRecord) -> str:
    data = milestone.data if isinstance(milestone.data, dict) else {}
    return str(data.get("tipo") or MILESTONE_TIPO_SPRINT_LEGACY)


def is_backlog_milestone(milestone: ProjectRecord) -> bool:
    return milestone.record_type == "milestone" and milestone_tipo(milestone) == MILESTONE_TIPO_BACKLOG


def is_sprint_milestone(milestone: ProjectRecord) -> bool:
    if milestone.record_type != "milestone":
        return False
    tipo = milestone_tipo(milestone)
    return tipo in (MILESTONE_TIPO_SPRINT, MILESTONE_TIPO_SPRINT_LEGACY)


def get_product_backlog_milestone(
    db: Session, project_id: uuid.UUID
) -> ProjectRecord | None:
    rows = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type == "milestone",
            )
        )
    )
    for row in rows:
        if is_backlog_milestone(row):
            return row
    return None


def ensure_product_backlog_milestone(
    db: Session,
    project: Project,
    *,
    created_by: uuid.UUID | None = None,
) -> ProjectRecord:
    existing = get_product_backlog_milestone(db, project.id)
    if existing is not None:
        return existing
    actor = created_by or project.created_by
    row = ProjectRecord(
        project_id=project.id,
        record_type="milestone",
        parent_id=None,
        titulo=BACKLOG_MILESTONE_TITLE,
        descripcion="Contenedor del Product Backlog (épicas e historias sin sprint).",
        estado="pendiente",
        data={"tipo": MILESTONE_TIPO_BACKLOG},
        created_by=actor,
        orden=0,
    )
    db.add(row)
    db.flush()
    return row


def list_stories_for_sprint(
    db: Session,
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
) -> list[ProjectRecord]:
    rows = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type == "task",
                ProjectRecord.parent_id == sprint_id,
            )
        )
    )
    return [r for r in rows if get_scrum_role(r) == SCRUM_ROLE_STORY]


def list_stories_in_backlog(db: Session, project_id: uuid.UUID) -> list[ProjectRecord]:
    backlog = get_product_backlog_milestone(db, project_id)
    if backlog is None:
        return []
    rows = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type == "task",
                ProjectRecord.parent_id == backlog.id,
            )
        )
    )
    return [r for r in rows if get_scrum_role(r) == SCRUM_ROLE_STORY]


def list_epic_tasks(db: Session, project_id: uuid.UUID) -> list[ProjectRecord]:
    backlog = get_product_backlog_milestone(db, project_id)
    if backlog is None:
        return []
    rows = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type == "task",
                ProjectRecord.parent_id == backlog.id,
            )
        )
    )
    return [r for r in rows if get_scrum_role(r) == SCRUM_ROLE_EPIC]


def list_dev_tasks_for_story(
    db: Session, project_id: uuid.UUID, story_id: uuid.UUID
) -> list[ProjectRecord]:
    story_key = str(story_id)
    rows = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type == "task",
            )
        )
    )
    out: list[ProjectRecord] = []
    for row in rows:
        if get_scrum_role(row) != SCRUM_ROLE_DEV:
            continue
        data = row.data if isinstance(row.data, dict) else {}
        if str(data.get("parent_task_id") or "") == story_key:
            out.append(row)
    return out


def story_in_product_backlog(story: ProjectRecord, backlog: ProjectRecord | None) -> bool:
    if not is_scrum_story(story) or backlog is None:
        return False
    return story.parent_id == backlog.id


def apply_scrum_v2_structure(db: Session, project: Project) -> None:
    """Idempotente: task-first Scrum (sprint raíz, scrum_role en tasks)."""
    if not is_scrum_template(getattr(project, "template_slug", None)):
        return

    task_rt = db.scalar(
        select(ProjectRecordType).where(
            ProjectRecordType.project_id == project.id,
            ProjectRecordType.key == "task",
        )
    )
    if task_rt is not None:
        task_rt.parent_types = ["milestone"]
        task_rt.label = "Tarea"

    milestone_rt = db.scalar(
        select(ProjectRecordType).where(
            ProjectRecordType.project_id == project.id,
            ProjectRecordType.key == "milestone",
        )
    )
    if milestone_rt is not None:
        milestone_rt.label = "Sprint"

    _ensure_scrum_role_field(db, project)
    _patch_scope_block_for_scrum_v2(db, project)
    _patch_milestone_tipo_field(db, project)
    _sunset_legacy_scrum_entity_types(db, project)
    ensure_product_backlog_milestone(db, project)
    db.flush()


def _sunset_legacy_scrum_entity_types(db: Session, project: Project) -> None:
    """Oculta tipos legacy epic/feature en Scrum v2 (no usados en UI)."""
    for legacy_key in ("epic", "feature"):
        row = db.scalar(
            select(ProjectRecordType).where(
                ProjectRecordType.project_id == project.id,
                ProjectRecordType.key == legacy_key,
            )
        )
        if row is not None:
            db.delete(row)


def _ensure_scrum_role_field(db: Session, project: Project) -> None:
    existing = db.scalar(
        select(ProjectFieldDefinition.id).where(
            ProjectFieldDefinition.project_id == project.id,
            ProjectFieldDefinition.entity_type_key == "task",
            ProjectFieldDefinition.field_key == "scrum_role",
        )
    )
    if existing:
        return
    db.add(
        ProjectFieldDefinition(
            project_id=project.id,
            entity_type_key="task",
            field_key="scrum_role",
            label="Rol Scrum",
            field_type="select",
            config={
                "options": [SCRUM_ROLE_EPIC, SCRUM_ROLE_STORY, SCRUM_ROLE_DEV],
            },
            orden=50,
            is_system=True,
        )
    )


def _patch_milestone_tipo_field(db: Session, project: Project) -> None:
    row = db.scalar(
        select(ProjectFieldDefinition).where(
            ProjectFieldDefinition.project_id == project.id,
            ProjectFieldDefinition.entity_type_key == "milestone",
            ProjectFieldDefinition.field_key == "tipo",
        )
    )
    if row is None:
        return
    config = dict(row.config or {})
    config["options"] = [MILESTONE_TIPO_BACKLOG, MILESTONE_TIPO_SPRINT, MILESTONE_TIPO_SPRINT_LEGACY]
    config["default"] = MILESTONE_TIPO_SPRINT
    row.config = config


def _patch_scope_block_for_scrum_v2(db: Session, project: Project) -> None:
    block = db.scalar(
        select(ProjectBlock).where(
            ProjectBlock.project_id == project.id,
            ProjectBlock.key == "scope",
        )
    )
    if block is None:
        return
    config = dict(block.config or {})
    scope_config = dict(config.get("scope_config") or {})
    scope_config["levels"] = ["milestone", "task"]
    config["scope_config"] = scope_config
    block.config = config


def resolve_workflow_for_scrum_task(
    db: Session,
    project: Project,
    record: ProjectRecord,
) -> dict[str, Any] | None:
    from app.domain.workflow_templates import (
        default_task_workflow,
        default_task_workflow_epic_container,
        default_task_workflow_scrum_story_cliente,
        default_task_workflow_scrum_story_interno,
    )
    from app.services.workflow.store import get_active_workflow

    role = get_scrum_role(record)
    if role == SCRUM_ROLE_STORY:
        slug = getattr(project, "template_slug", None)
        if slug == "t7_scrum_cliente":
            return default_task_workflow_scrum_story_cliente()
        return default_task_workflow_scrum_story_interno()
    if role == SCRUM_ROLE_EPIC:
        return default_task_workflow_epic_container()
    wf = get_active_workflow(db, project.id, "task")
    return wf or default_task_workflow()
