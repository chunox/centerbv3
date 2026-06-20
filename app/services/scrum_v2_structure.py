"""Scrum v2: sprint/backlog propios, épicas e historias como tasks (scrum_role)."""
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
    ProjectWorkflowDefinition,
)

from app.domain.project_templates import SCRUM_TEMPLATE_SLUGS, is_scrum_template_slug
from app.domain.records.types import RecordRef

SCRUM_ROLE_EPIC = "epic"
SCRUM_ROLE_STORY = "story"
SCRUM_ROLE_DEV = "dev"

SCRUM_STORY_STATE_BACKLOG = "product_backlog"
SCRUM_STORY_STATE_PLANNED = "planificado"

# Legacy: milestones con data.tipo (pre-migración)
MILESTONE_TIPO_BACKLOG = "product_backlog"
MILESTONE_TIPO_SPRINT = "sprint"
MILESTONE_TIPO_SPRINT_LEGACY = "entrega"

BACKLOG_TITLE = "Product Backlog"


def is_scrum_template(template_slug: str | None) -> bool:
    return is_scrum_template_slug(template_slug)


def get_scrum_role(record: ProjectRecord) -> str | None:
    data = record.data if isinstance(record.data, dict) else {}
    role = data.get("scrum_role")
    return str(role) if role in (SCRUM_ROLE_EPIC, SCRUM_ROLE_STORY, SCRUM_ROLE_DEV) else None


def is_scrum_story(record: ProjectRecord) -> bool:
    return record.record_type == "task" and get_scrum_role(record) == SCRUM_ROLE_STORY


def is_scrum_story_planned(record: ProjectRecord) -> bool:
    return is_scrum_story(record) and record.estado == SCRUM_STORY_STATE_PLANNED


def is_scrum_story_on_sprint_board(record: ProjectRecord) -> bool:
    """Historia activa en Sprint Board (excluye backlog y planificación pendiente)."""
    if not is_scrum_story(record):
        return False
    return record.estado not in {
        SCRUM_STORY_STATE_BACKLOG,
        SCRUM_STORY_STATE_PLANNED,
    }


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


def _milestone_tipo(milestone: ProjectRecord) -> str:
    data = milestone.data if isinstance(milestone.data, dict) else {}
    return str(data.get("tipo") or MILESTONE_TIPO_SPRINT_LEGACY)


def is_product_backlog_record(record: ProjectRecord) -> bool:
    if record.record_type == "product_backlog":
        return True
    return record.record_type == "milestone" and _milestone_tipo(record) == MILESTONE_TIPO_BACKLOG


def is_sprint_record(record: ProjectRecord) -> bool:
    if record.record_type == "sprint":
        return True
    if record.record_type != "milestone":
        return False
    tipo = _milestone_tipo(record)
    return tipo in (MILESTONE_TIPO_SPRINT, MILESTONE_TIPO_SPRINT_LEGACY)


# Aliases legacy
is_backlog_milestone = is_product_backlog_record
is_sprint_milestone = is_sprint_record


def get_product_backlog_record(
    db: Session, project_id: uuid.UUID
) -> ProjectRecord | None:
    row = db.scalar(
        select(ProjectRecord).where(
            ProjectRecord.project_id == project_id,
            ProjectRecord.record_type == "product_backlog",
        )
    )
    if row is not None:
        return row
    rows = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type == "milestone",
            )
        )
    )
    for row in rows:
        if is_product_backlog_record(row):
            return row
    return None


get_product_backlog_milestone = get_product_backlog_record


def ensure_product_backlog_record(
    db: Session,
    project: Project,
    *,
    created_by: uuid.UUID | None = None,
) -> ProjectRecord:
    existing = get_product_backlog_record(db, project.id)
    if existing is not None:
        return existing
    actor = created_by or project.created_by
    row = ProjectRecord(
        project_id=project.id,
        record_type="product_backlog",
        parent_id=None,
        titulo=BACKLOG_TITLE,
        descripcion="Contenedor del Product Backlog (épicas e historias sin sprint).",
        estado="activo",
        data={},
        created_by=actor,
        orden=0,
    )
    db.add(row)
    db.flush()
    return row


ensure_product_backlog_milestone = ensure_product_backlog_record


def next_sprint_orden(db: Session, project_id: uuid.UUID) -> int:
    from app.services.records.repository import list_records

    sprints = list_records(db, project_id, entity_type="sprint")
    legacy = [
        r
        for r in list_records(db, project_id, entity_type="milestone")
        if is_sprint_record(r)
    ]
    return len(sprints) + len(legacy) + 1


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
    backlog = get_product_backlog_record(db, project_id)
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


def list_stories_for_epic(
    db: Session,
    project_id: uuid.UUID,
    epic_id: uuid.UUID,
) -> list[ProjectRecord]:
    epic_key = str(epic_id)
    rows = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type == "task",
            )
        )
    )
    return [
        r
        for r in rows
        if get_scrum_role(r) == SCRUM_ROLE_STORY
        and str((r.data or {}).get("epic_task_id") or "") == epic_key
    ]


def list_epic_tasks(db: Session, project_id: uuid.UUID) -> list[ProjectRecord]:
    backlog = get_product_backlog_record(db, project_id)
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


def reparent_scrum_story_to_sprint(
    db: Session,
    project: Project,
    story: ProjectRecord,
    sprint_id: uuid.UUID,
    *,
    sync_source_sprint: bool = True,
) -> None:
    """Mueve historia (y dev tasks) a un sprint sin cambiar su estado de workflow."""
    sprint = db.get(ProjectRecord, sprint_id)
    if sprint is None or sprint.project_id != project.id or not is_sprint_record(sprint):
        return

    source_sprint_id = story.parent_id
    story.parent_id = sprint_id
    db.flush()

    from app.services.scrum_effort import maybe_sync_scrum_on_sprint_assignment

    maybe_sync_scrum_on_sprint_assignment(db, project, story)

    if is_scrum_story(story):
        for dev in list_dev_tasks_for_story(db, project.id, story.id):
            dev.parent_id = sprint_id
        db.flush()

    from app.services.scrum_metrics import sync_sprint_horas_planeadas

    sync_sprint_horas_planeadas(db, sprint, commit=False)

    if sync_source_sprint and source_sprint_id is not None:
        previous_sprint = db.get(ProjectRecord, source_sprint_id)
        if (
            previous_sprint is not None
            and previous_sprint.project_id == project.id
            and is_sprint_record(previous_sprint)
            and previous_sprint.id != sprint_id
        ):
            sync_sprint_horas_planeadas(db, previous_sprint, commit=False)


def reparent_scrum_story_to_backlog(
    db: Session,
    project: Project,
    story: ProjectRecord,
    actor_user_id: uuid.UUID,
) -> None:
    """Devuelve historia (y dev tasks) al Product Backlog listos para re-comprometer."""
    from app.services.records.repository import update_record_fields
    from app.services.workflow.engine import apply_record_transition

    if story.estado in {"pendiente", SCRUM_STORY_STATE_PLANNED}:
        apply_record_transition(
            db,
            project,
            story,
            record_ref=RecordRef(
                id=story.id,
                record_type=story.record_type,
                project_id=project.id,
            ),
            action_id="volver_al_backlog",
            actor_user_id=actor_user_id,
        )
        return

    previous_sprint_id = story.parent_id
    backlog = ensure_product_backlog_record(db, project, created_by=actor_user_id)
    story.parent_id = backlog.id
    db.flush()

    if is_scrum_story(story):
        for dev in list_dev_tasks_for_story(db, project.id, story.id):
            dev.parent_id = backlog.id
        db.flush()

    if story.estado not in {"completado", "cancelado", "product_backlog"}:
        update_record_fields(db, story, estado="product_backlog")

    if previous_sprint_id is not None:
        previous_sprint = db.get(ProjectRecord, previous_sprint_id)
        if (
            previous_sprint is not None
            and previous_sprint.project_id == project.id
            and is_sprint_record(previous_sprint)
        ):
            from app.services.scrum_metrics import sync_sprint_horas_planeadas

            sync_sprint_horas_planeadas(db, previous_sprint, commit=False)


def apply_scrum_v2_structure(db: Session, project: Project) -> None:
    """Idempotente: task-first Scrum con tipos sprint/product_backlog propios."""
    if not is_scrum_template(getattr(project, "template_slug", None)):
        return

    _ensure_scrum_record_types(db, project)
    _ensure_scrum_role_field(db, project)
    _patch_query_report_parent_types(db, project)
    _patch_scope_block_for_scrum_v2(db, project)
    _sunset_legacy_scrum_entity_types(db, project)
    _remove_legacy_feature_workflow(db, project)
    ensure_product_backlog_record(db, project)
    db.flush()


def _ensure_scrum_record_types(db: Session, project: Project) -> None:
    task_rt = db.scalar(
        select(ProjectRecordType).where(
            ProjectRecordType.project_id == project.id,
            ProjectRecordType.key == "task",
        )
    )
    if task_rt is not None:
        task_rt.parent_types = ["product_backlog", "sprint"]
        task_rt.label = "Tarea"

    for key, label in (("sprint", "Sprint"), ("product_backlog", "Product Backlog")):
        rt = db.scalar(
            select(ProjectRecordType).where(
                ProjectRecordType.project_id == project.id,
                ProjectRecordType.key == key,
            )
        )
        if rt is None:
            db.add(
                ProjectRecordType(
                    project_id=project.id,
                    key=key,
                    label=label,
                    parent_types=None,
                    is_system=True,
                    orden=7 if key == "product_backlog" else 8,
                )
            )

    milestone_rt = db.scalar(
        select(ProjectRecordType).where(
            ProjectRecordType.project_id == project.id,
            ProjectRecordType.key == "milestone",
        )
    )
    if milestone_rt is not None:
        db.delete(milestone_rt)

    impediment_rt = db.scalar(
        select(ProjectRecordType).where(
            ProjectRecordType.project_id == project.id,
            ProjectRecordType.key == "impediment",
        )
    )
    if impediment_rt is not None:
        impediment_rt.parent_types = ["sprint"]


def _patch_query_report_parent_types(db: Session, project: Project) -> None:
    """Query/report en Scrum: parent = task (historia), no feature."""
    for entity_key in ("query", "report"):
        rt = db.scalar(
            select(ProjectRecordType).where(
                ProjectRecordType.project_id == project.id,
                ProjectRecordType.key == entity_key,
            )
        )
        if rt is not None:
            rt.parent_types = ["task"]


def _remove_legacy_feature_workflow(db: Session, project: Project) -> None:
    rows = list(
        db.scalars(
            select(ProjectWorkflowDefinition).where(
                ProjectWorkflowDefinition.project_id == project.id,
                ProjectWorkflowDefinition.entity_type == "feature",
            )
        )
    )
    for row in rows:
        db.delete(row)


def _sunset_legacy_scrum_entity_types(db: Session, project: Project) -> None:
    """Oculta tipos legacy epic/feature/milestone en Scrum v2."""
    for legacy_key in ("epic", "feature", "milestone"):
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
    scope_config["levels"] = ["product_backlog", "sprint", "task"]
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
        default_task_workflow_scrum_dev,
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
    if role == SCRUM_ROLE_DEV:
        return default_task_workflow_scrum_dev()
    wf = get_active_workflow(db, project.id, "task")
    return wf or default_task_workflow_scrum_dev()
