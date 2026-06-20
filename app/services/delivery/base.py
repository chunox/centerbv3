"""Protocolo común para servicios de entrega por modo."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.records.types import RecordDTO
from app.models.entities import Project, ProjectRecord
from app.schemas.records import RecordCreate, RecordMigrateRequest, RecordTransitionRequest


class DeliveryService(ABC):
    """Operaciones de dominio de entrega delegadas desde project_records."""

    @abstractmethod
    def assert_task_create(
        self,
        db: Session,
        project: Project,
        payload: RecordCreate,
        actor_user_id: UUID,
    ) -> None:
        ...

    @abstractmethod
    def create_record(
        self,
        db: Session,
        project: Project,
        payload: RecordCreate,
        actor_user_id: UUID,
    ) -> RecordDTO:
        ...

    @abstractmethod
    def migrate_record(
        self,
        db: Session,
        project: Project,
        work_item: ProjectRecord,
        payload: RecordMigrateRequest,
        actor_user_id: UUID,
    ) -> RecordDTO:
        ...

    def list_effort_map(
        self,
        db: Session,
        project: Project,
        record_type: str,
        rows: list[RecordDTO],
    ) -> dict[UUID, float]:
        return {}

    def validate_in_product_backlog_filter(
        self, project: Project, record_type: str
    ) -> None:
        raise HTTPException(
            status_code=422,
            detail="in_product_backlog solo aplica a proyectos Scrum",
        )

    def transition_record(
        self,
        db: Session,
        project: Project,
        row: ProjectRecord,
        payload: RecordTransitionRequest,
        actor_user_id: UUID,
    ) -> RecordDTO | None:
        """None = delegar al flujo genérico (generic_store.transition_record)."""
        return None

    def after_create(
        self,
        db: Session,
        project: Project,
        row: ProjectRecord,
        *,
        record_type: str,
    ) -> None:
        ...

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
        ...

    def after_transition(
        self,
        db: Session,
        project: Project,
        record: ProjectRecord,
        *,
        actor_user_id: UUID,
        from_state: str | None = None,
    ) -> None:
        ...

    def assert_task_transition(
        self,
        db: Session,
        project: Project,
        record: ProjectRecord,
        *,
        action_id: str,
        target_state: str | None,
        actor_user_id: UUID,
    ) -> None:
        """Validaciones de dominio antes de aplicar transición en tasks."""
        ...

    def filter_list_by_sprint(
        self,
        db: Session,
        rows: list[ProjectRecord],
        sprint_id: UUID,
    ) -> list[ProjectRecord]:
        return rows

    def resolve_record_workflow(
        self,
        db: Session,
        project: Project,
        record: ProjectRecord,
    ) -> dict[str, Any] | None:
        from app.services.workflow.store import get_active_workflow

        return get_active_workflow(db, project.id, record.record_type)

    def build_access_workflows(
        self,
        db: Session,
        project: Project,
    ) -> dict[str, Any]:
        from app.schemas.access_context import WorkflowSummaryRead, workflow_summary_from_definition
        from app.services.workflow.store import (
            get_active_workflow,
            get_active_workflow_version,
            workflow_entity_types,
        )

        workflows: dict[str, WorkflowSummaryRead] = {}
        for entity_type in workflow_entity_types(db, project.id):
            defn = get_active_workflow(db, project.id, entity_type)
            if defn is None:
                continue
            version = get_active_workflow_version(db, project.id, entity_type) or 1
            workflows[entity_type] = workflow_summary_from_definition(
                entity_type, version, defn
            )
        return workflows

    def list_uat_gate_child_tasks(
        self,
        db: Session,
        project: Project,
        entity: ProjectRecord,
    ) -> list[ProjectRecord] | None:
        if entity.record_type != "feature":
            return None
        from app.services.records.repository import list_children

        return list_children(db, entity.id, "task")

    def record_in_product_backlog(self, db: Session, row: ProjectRecord) -> bool:
        return False

    def check_parent_is_sprint_gate(
        self, db: Session, entity: ProjectRecord
    ) -> None:
        raise HTTPException(
            status_code=409,
            detail="Gate parent_is_sprint no aplica en modo waterfall",
        )
