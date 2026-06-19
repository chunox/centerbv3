"""Operaciones de entrega Scrum (product_backlog, sprint, epic/story/dev tasks)."""
from __future__ import annotations

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
from app.services.features import migrate_feature
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
        migrate_feature(
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

    def after_transition(
        self,
        db: Session,
        project: Project,
        record: ProjectRecord,
        *,
        actor_user_id: UUID,
    ) -> None:
        from app.services.scrum_tasks import sync_story_from_dev_tasks
        from app.services.scrum_v2_structure import get_story_task_id, is_scrum_dev_task

        if record.record_type != "task" or not is_scrum_dev_task(record):
            return
        story_id = get_story_task_id(record)
        if not story_id:
            return
        story = db.get(ProjectRecord, story_id)
        if story is not None:
            sync_story_from_dev_tasks(
                db, story, project, actor_user_id=actor_user_id
            )

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
