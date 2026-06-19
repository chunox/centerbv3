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
    ) -> None:
        ...

    def filter_list_by_sprint(
        self,
        db: Session,
        rows: list[ProjectRecord],
        sprint_id: UUID,
    ) -> list[ProjectRecord]:
        return rows
