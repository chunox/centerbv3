"""Operaciones de entrega Scrum (product_backlog, sprint, epic/story/dev tasks)."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.capabilities import (
    KANBAN_TASK_CREATE,
    SCOPE_EPIC_CREATE,
    SCOPE_FEATURE_CREATE,
    SCOPE_STORY_CREATE,
)
from app.domain.records.types import RecordDTO
from app.models.entities import Project, ProjectRecord
from app.schemas.records import RecordCreate, RecordMigrateRequest
from app.services.delivery.base import DeliveryService
from app.services.records import generic_store
from app.services.scrum_effort import (
    batch_feature_effort_hours,
    get_scrum_item_sprint_id,
)
from app.services.scrum_tasks import (
    create_dev_subtask,
    create_dev_task,
    create_epic_task,
    create_story_task,
    migrate_story_sprint,
)
from app.services.scrum_v2_structure import (
    SCRUM_ROLE_DEV,
    SCRUM_ROLE_EPIC,
    SCRUM_ROLE_STORY,
    is_scrum_dev_task,
    is_scrum_story,
    next_sprint_orden,
)
from app.services.workflow.authorize import assert_any_capability, assert_capability


class ScrumRecordService(DeliveryService):
    def assert_task_create(
        self,
        db: Session,
        project: Project,
        payload: RecordCreate,
        actor_user_id: UUID,
    ) -> None:
        from app.services.workflow.authorize import assert_capability as _assert_cap

        task_data = dict(payload.data or {})
        scrum_role = task_data.get("scrum_role")

        if scrum_role == SCRUM_ROLE_EPIC:
            assert_any_capability(
                db,
                project.id,
                actor_user_id,
                [
                    SCOPE_EPIC_CREATE,
                    "record.epic.create",
                    "record.task.create",
                    KANBAN_TASK_CREATE,
                ],
                detail="Sin permisos para crear épicas",
            )
            return
        if scrum_role == SCRUM_ROLE_STORY:
            assert_any_capability(
                db,
                project.id,
                actor_user_id,
                [
                    SCOPE_STORY_CREATE,
                    SCOPE_FEATURE_CREATE,
                    "record.feature.create",
                    "record.task.create",
                    KANBAN_TASK_CREATE,
                ],
                detail="Sin permisos para crear historias",
            )
            return
        if scrum_role == SCRUM_ROLE_DEV or task_data.get("parent_task_id"):
            _assert_cap(db, project.id, actor_user_id, KANBAN_TASK_CREATE)
            return

        from app.services.delivery.caps import assert_record_cap

        assert_record_cap(db, project.id, actor_user_id, "record.task.create")
        assert_capability(db, project.id, actor_user_id, KANBAN_TASK_CREATE)

    def create_record(
        self,
        db: Session,
        project: Project,
        payload: RecordCreate,
        actor_user_id: UUID,
    ) -> RecordDTO:
        if payload.record_type == "report":
            return self._create_report(db, project, payload, actor_user_id)
        if payload.record_type == "task":
            return self._create_task(db, project, payload, actor_user_id)
        if payload.record_type == "sprint":
            return generic_store.create_record(
                db,
                project,
                record_type="sprint",
                titulo=payload.titulo,
                created_by=actor_user_id,
                descripcion=payload.descripcion,
                parent_id=payload.parent_id,
                data=payload.data or {},
                fecha_inicio=payload.fecha_inicio,
                fecha_fin=payload.fecha_fin,
                assignee_ids=payload.assignee_ids,
                initial_state=payload.initial_state or "pendiente",
                orden=next_sprint_orden(db, project.id),
            )
        return generic_store.create_record(
            db,
            project,
            record_type=payload.record_type,
            titulo=payload.titulo,
            created_by=actor_user_id,
            descripcion=payload.descripcion,
            parent_id=payload.parent_id,
            data=payload.data,
            fecha_inicio=payload.fecha_inicio,
            fecha_fin=payload.fecha_fin,
            assignee_ids=payload.assignee_ids,
            initial_state=payload.initial_state,
            orden=payload.orden,
        )

    def migrate_record(
        self,
        db: Session,
        project: Project,
        work_item: ProjectRecord,
        payload: RecordMigrateRequest,
        actor_user_id: UUID,
    ) -> RecordDTO:
        from app.api.v1.deps import get_milestone_or_404

        if not is_scrum_story(work_item):
            raise HTTPException(status_code=404, detail="Historia no encontrada")
        sprint_id = get_scrum_item_sprint_id(db, work_item)
        if sprint_id is None:
            raise HTTPException(
                status_code=409,
                detail="La historia no está asignada a un sprint",
            )
        source_milestone = get_milestone_or_404(project.id, sprint_id, db)
        target_milestone = get_milestone_or_404(
            project.id, payload.target_milestone_id, db
        )
        migrate_story_sprint(
            db,
            work_item,
            project,
            source_milestone,
            target_milestone,
            actor_user_id=actor_user_id,
        )
        dto = generic_store.get_record(db, work_item.id)
        if dto is None:
            raise HTTPException(status_code=404, detail="Registro no encontrado")
        return dto

    def list_effort_map(
        self,
        db: Session,
        project: Project,
        record_type: str,
        rows: list[RecordDTO],
    ) -> dict[UUID, float]:
        if record_type not in ("feature", "task"):
            return {}
        item_ids = [r.id for r in rows]
        return batch_feature_effort_hours(db, project.id, item_ids)

    def validate_in_product_backlog_filter(
        self, project: Project, record_type: str
    ) -> None:
        if record_type not in ("feature", "task"):
            raise HTTPException(
                status_code=422,
                detail="in_product_backlog requiere record_type=feature o task",
            )

    def _create_report(
        self,
        db: Session,
        project: Project,
        payload: RecordCreate,
        actor_user_id: UUID,
    ) -> RecordDTO:
        from app.config import settings
        from app.domain.capabilities import REPORT_CREATE
        from app.services.feature_reports import notify_pms_report_received
        from app.services.project_profile import supports_reports

        if payload.parent_id is None:
            raise HTTPException(status_code=422, detail="parent_id requerido para reportes")
        parent = db.get(ProjectRecord, payload.parent_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="Registro padre no encontrado")
        if not is_scrum_story(parent):
            raise HTTPException(
                status_code=422,
                detail="En Scrum el reporte debe referenciar una historia (task con scrum_role=story)",
            )
        assert_capability(db, project.id, actor_user_id, REPORT_CREATE)
        if parent.estado != "completado":
            raise HTTPException(
                status_code=409,
                detail="Solo se puede reportar sobre un ítem en estado completado",
            )
        if not supports_reports(db, project):
            raise HTTPException(
                status_code=400,
                detail="Los reportes solo aplican a proyectos con stakeholder externo",
            )
        data = dict(payload.data or {})
        data.setdefault("reported_by", str(actor_user_id))
        dto = generic_store.create_record(
            db,
            project,
            record_type=payload.record_type,
            titulo=payload.titulo,
            created_by=actor_user_id,
            descripcion=payload.descripcion,
            parent_id=payload.parent_id,
            data=data,
            fecha_inicio=payload.fecha_inicio,
            fecha_fin=payload.fecha_fin,
            assignee_ids=payload.assignee_ids,
            initial_state=payload.initial_state,
            orden=payload.orden,
        )
        if not settings.communication_rules_only:
            notify_pms_report_received(db, project, db.get(ProjectRecord, dto.id))
        return dto

    def _create_task(
        self,
        db: Session,
        project: Project,
        payload: RecordCreate,
        actor_user_id: UUID,
    ) -> RecordDTO:
        task_data = dict(payload.data or {})
        scrum_role = task_data.get("scrum_role")

        if scrum_role == SCRUM_ROLE_EPIC:
            row = create_epic_task(
                db,
                project,
                titulo=payload.titulo,
                created_by=actor_user_id,
                descripcion=payload.descripcion,
            )
            dto = generic_store.get_record(db, row.id)
            assert dto is not None
            return dto

        if scrum_role == SCRUM_ROLE_STORY:
            epic_raw = task_data.get("epic_task_id")
            if not epic_raw:
                raise HTTPException(
                    status_code=422, detail="epic_task_id requerido para historias"
                )
            row = create_story_task(
                db,
                project,
                titulo=payload.titulo,
                created_by=actor_user_id,
                epic_task_id=UUID(str(epic_raw)),
                descripcion=payload.descripcion,
                prioridad=str(task_data.get("prioridad") or "media"),
                initial_state=payload.initial_state or "product_backlog",
                data=task_data,
            )
            dto = generic_store.get_record(db, row.id)
            assert dto is not None
            return dto

        if scrum_role == SCRUM_ROLE_DEV or task_data.get("parent_task_id"):
            story_raw = task_data.get("parent_task_id")
            if not story_raw:
                raise HTTPException(
                    status_code=422, detail="parent_task_id requerido para tareas dev"
                )
            parent_record = db.get(ProjectRecord, UUID(str(story_raw)))
            if parent_record is not None and is_scrum_dev_task(parent_record):
                row = create_dev_subtask(
                    db,
                    project,
                    titulo=payload.titulo,
                    created_by=actor_user_id,
                    parent_dev_id=parent_record.id,
                    descripcion=payload.descripcion,
                    data=task_data,
                    initial_state=payload.initial_state,
                    assignee_ids=payload.assignee_ids,
                )
            else:
                row = create_dev_task(
                    db,
                    project,
                    titulo=payload.titulo,
                    created_by=actor_user_id,
                    story_id=UUID(str(story_raw)),
                    descripcion=payload.descripcion,
                    data=task_data,
                    initial_state=payload.initial_state,
                    assignee_ids=payload.assignee_ids,
                )
            dto = generic_store.get_record(db, row.id)
            assert dto is not None
            return dto

        raise HTTPException(
            status_code=422,
            detail="En Scrum las tareas requieren data.scrum_role (epic, story o dev)",
        )

    def after_create(
        self,
        db: Session,
        project: Project,
        row: ProjectRecord,
        *,
        record_type: str,
    ) -> None:
        from app.services.scrum_effort import maybe_sync_scrum_on_sprint_assignment

        if record_type == "feature":
            maybe_sync_scrum_on_sprint_assignment(db, project, row)

    def after_update(
        self,
        db: Session,
        project: Project,
        record: ProjectRecord,
        *,
        data: dict | None,
        old_parent_id,
        old_fecha_inicio,
        old_fecha_fin,
    ) -> None:
        from app.services.scrum_effort import (
            maybe_propagate_scrum_sprint_dates,
            maybe_sync_scrum_on_sprint_assignment,
        )

        if record.record_type == "feature" and data is not None:
            maybe_sync_scrum_on_sprint_assignment(db, project, record)
        if record.record_type in ("milestone", "sprint"):
            fecha_changed = (
                record.fecha_inicio != old_fecha_inicio
                or record.fecha_fin != old_fecha_fin
            )
            maybe_propagate_scrum_sprint_dates(
                db, project, record, fecha_changed=fecha_changed
            )
        if (
            record.record_type == "task"
            and data is not None
            and "estimacion_horas" in data
        ):
            from app.services.scrum_effort import get_scrum_item_sprint_id
            from app.services.scrum_metrics import sync_sprint_horas_planeadas
            from app.services.scrum_v2_structure import is_scrum_dev_task

            if is_scrum_dev_task(record):
                sprint_id = get_scrum_item_sprint_id(db, record)
                if sprint_id is not None:
                    sprint = db.get(ProjectRecord, sprint_id)
                    if (
                        sprint is not None
                        and sprint.project_id == project.id
                    ):
                        sync_sprint_horas_planeadas(db, sprint, commit=False)

    def after_transition(
        self,
        db: Session,
        project: Project,
        record: ProjectRecord,
        *,
        actor_user_id: UUID,
        from_state: str | None = None,
        side_effect_context: dict[str, Any] | None = None,
    ) -> None:
        from app.services.scrum_parent_cascade import (
            apply_scrum_parent_cascade,
            list_scrum_children_for_cascade,
        )
        from app.services.scrum_v2_structure import (
            is_scrum_dev_task,
            is_scrum_epic_task,
            is_scrum_story,
        )

        if record.record_type != "task":
            return

        ctx = side_effect_context or {}
        cascade_only = from_state == record.estado and bool(ctx.get("cascade_target_state"))

        if from_state == record.estado and not cascade_only:
            return

        if is_scrum_story(record) and not cascade_only:
            self._maybe_sync_sprint_horas(
                db, project, record, from_state=from_state
            )

        if not (
            is_scrum_epic_task(record)
            or is_scrum_story(record)
            or is_scrum_dev_task(record)
        ):
            return

        if not list_scrum_children_for_cascade(db, project, record):
            return

        raw_mode = ctx.get("cascade_mode", "all")
        mode = raw_mode if raw_mode in {
            "all",
            "none",
            "cancel_backlog_then_sprint",
            "cascade_backlog",
        } else "all"

        from app.services.scrum_parent_cascade import resolve_cascade_target_state

        cascade_state = resolve_cascade_target_state(
            record,
            target_state=record.estado,
            cascade_target_state=ctx.get("cascade_target_state"),
        )

        apply_scrum_parent_cascade(
            db,
            project,
            record,
            target_state=cascade_state,
            actor_user_id=actor_user_id,
            mode=mode,
            side_effect_context=ctx,
        )

    def _maybe_sync_sprint_horas(
        self,
        db: Session,
        project: Project,
        record: ProjectRecord,
        *,
        from_state: str | None,
    ) -> None:
        from app.services.scrum_effort import get_scrum_item_sprint_id
        from app.services.scrum_metrics import sync_sprint_horas_completadas
        from app.services.scrum_v2_structure import is_scrum_story

        if not is_scrum_story(record):
            return
        to_state = record.estado
        if from_state == to_state:
            return
        if from_state != "completado" and to_state != "completado":
            return
        sprint_id = get_scrum_item_sprint_id(db, record)
        if sprint_id is None:
            return
        sprint = db.get(ProjectRecord, sprint_id)
        if sprint is None or sprint.project_id != project.id:
            return
        sync_sprint_horas_completadas(db, sprint, commit=False)

    def filter_list_by_sprint(
        self,
        db: Session,
        rows: list[ProjectRecord],
        sprint_id: UUID,
    ) -> list[ProjectRecord]:
        from app.services.scrum_v2_structure import is_scrum_story

        sprint_key = str(sprint_id)
        return [
            r
            for r in rows
            if str((r.data or {}).get("sprint_id") or "") == sprint_key
            or (
                r.record_type == "task"
                and r.parent_id == sprint_id
                and is_scrum_story(r)
            )
        ]

    def resolve_record_workflow(
        self,
        db: Session,
        project: Project,
        record: ProjectRecord,
    ) -> dict[str, Any] | None:
        from app.services.scrum_v2_structure import (
            SCRUM_ROLE_DEV,
            SCRUM_ROLE_EPIC,
            SCRUM_ROLE_STORY,
            resolve_workflow_for_scrum_task,
        )
        from app.services.workflow.store import get_active_workflow

        if record.record_type == "task" and (record.data or {}).get("scrum_role") in (
            SCRUM_ROLE_EPIC,
            SCRUM_ROLE_STORY,
            SCRUM_ROLE_DEV,
        ):
            return resolve_workflow_for_scrum_task(db, project, record)
        return get_active_workflow(db, project.id, record.record_type)

    def build_access_workflows(
        self,
        db: Session,
        project: Project,
    ) -> dict[str, Any]:
        from app.domain.workflow_templates import (
            default_task_workflow_epic_container,
            default_task_workflow_scrum_dev,
            default_task_workflow_scrum_story_cliente,
            default_task_workflow_scrum_story_interno,
        )
        from app.schemas.access_context import workflow_summary_from_definition

        workflows = super().build_access_workflows(db, project)
        slug = project.template_slug or ""
        if slug == "t7_scrum_cliente":
            story_wf = default_task_workflow_scrum_story_cliente()
        else:
            story_wf = default_task_workflow_scrum_story_interno()
        workflows["story"] = workflow_summary_from_definition("story", 1, story_wf)
        epic_wf = default_task_workflow_epic_container()
        workflows["epic"] = workflow_summary_from_definition("epic", 1, epic_wf)
        dev_wf = default_task_workflow_scrum_dev()
        workflows["dev"] = workflow_summary_from_definition("dev", 1, dev_wf)
        workflows["task"] = workflows["dev"]
        workflows.pop("feature", None)
        return workflows

    def list_uat_gate_child_tasks(
        self,
        db: Session,
        project: Project,
        entity: ProjectRecord,
    ) -> list[ProjectRecord] | None:
        from app.services.scrum_v2_structure import (
            is_scrum_story,
            list_all_dev_tasks_for_story,
        )

        if not is_scrum_story(entity):
            return None
        return list_all_dev_tasks_for_story(db, project.id, entity.id)

    def record_in_product_backlog(self, db: Session, row: ProjectRecord) -> bool:
        from app.services.scrum_effort import is_record_in_product_backlog

        return is_record_in_product_backlog(db, row)

    def check_parent_is_sprint_gate(
        self, db: Session, entity: ProjectRecord
    ) -> None:
        from app.services.scrum_v2_structure import is_sprint_record

        if entity.parent_id is None:
            raise HTTPException(
                status_code=409, detail="La historia no está asignada a un sprint"
            )
        parent = db.get(ProjectRecord, entity.parent_id)
        if parent is None or not is_sprint_record(parent):
            raise HTTPException(
                status_code=409,
                detail="La historia no está planificada en un sprint",
            )
