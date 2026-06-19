"""Operaciones de entrega waterfall (milestone → feature → task)."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.capabilities import KANBAN_TASK_CREATE
from app.domain.records.types import RecordDTO
from app.models.entities import Project, ProjectRecord
from app.schemas.records import RecordCreate, RecordMigrateRequest
from app.services.delivery.base import DeliveryService
from app.services.features import migrate_feature, sync_feature_from_tasks
from app.services.milestones import next_milestone_orden
from app.services.records import generic_store
from app.services.tasks import sync_task_assignees
from app.services.workflow.authorize import assert_capability


class WaterfallRecordService(DeliveryService):
    def assert_task_create(
        self,
        db: Session,
        project: Project,
        payload: RecordCreate,
        actor_user_id: UUID,
    ) -> None:
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
        if payload.record_type == "milestone":
            return generic_store.create_record(
                db,
                project,
                record_type=payload.record_type,
                titulo=payload.titulo,
                created_by=actor_user_id,
                descripcion=payload.descripcion,
                parent_id=payload.parent_id,
                data=payload.data or {"tipo": "entrega"},
                fecha_inicio=payload.fecha_inicio,
                fecha_fin=payload.fecha_fin,
                assignee_ids=payload.assignee_ids,
                initial_state=payload.initial_state,
                orden=next_milestone_orden(db, project.id),
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

        if work_item.record_type != "feature":
            raise HTTPException(status_code=404, detail="Feature no encontrada")
        if work_item.parent_id is None:
            raise HTTPException(status_code=409, detail="Feature sin hito padre")
        source_milestone = get_milestone_or_404(
            project.id, work_item.parent_id, db
        )
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
        if parent is None or parent.record_type != "feature":
            raise HTTPException(status_code=404, detail="Feature no encontrada")
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
        from app.services.records.repository import _data

        if payload.parent_id is None:
            raise HTTPException(status_code=422, detail="parent_id requerido para tareas")
        feature = db.get(ProjectRecord, payload.parent_id)
        if feature is None or feature.record_type != "feature":
            raise HTTPException(status_code=404, detail="Feature no encontrada")
        if _data(feature).get("bloqueada"):
            raise HTTPException(
                status_code=409,
                detail="La feature está bloqueada; no se pueden crear tareas",
            )
        dto = generic_store.create_record(
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
            initial_state=payload.initial_state,
            orden=payload.orden,
        )
        task = db.get(ProjectRecord, dto.id)
        if payload.assignee_ids and task is not None:
            sync_task_assignees(
                db,
                task,
                project,
                actor_user_id=actor_user_id,
                user_ids=payload.assignee_ids,
            )
            sync_feature_from_tasks(
                db, feature, project, actor_user_id=actor_user_id
            )
            db.refresh(task)
            dto = generic_store.get_record(db, dto.id) or dto
        return dto
