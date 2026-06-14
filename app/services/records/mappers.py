"""Mapeo ProjectRecord → schemas Pydantic legacy."""
from __future__ import annotations

import uuid
from typing import Any

from app.models.entities import ProjectRecord
from app.schemas.records import RecordRead
from app.schemas.feature_queries import FeatureQueryRead
from app.schemas.feature_reports import FeatureReportRead
from app.schemas.features import FeatureRead
from app.schemas.milestones import MilestoneRead
from app.schemas.tasks import TaskRead
from app.services.records.repository import _data


def record_to_read(row: ProjectRecord, assignee_ids: list[uuid.UUID] | None = None) -> RecordRead:
    d = _data(row)
    return RecordRead(
        id=row.id,
        project_id=row.project_id,
        record_type=row.record_type,
        storage="generic",
        titulo=row.titulo,
        descripcion=row.descripcion,
        estado=row.estado,
        parent_id=row.parent_id,
        data=d,
        fecha_inicio=row.fecha_inicio,
        fecha_fin=row.fecha_fin,
        orden=row.orden,
        assignee_ids=assignee_ids or sorted(a.user_id for a in row.assignees),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def record_to_milestone_read(row: ProjectRecord) -> MilestoneRead:
    d = _data(row)
    return MilestoneRead(
        id=row.id,
        project_id=row.project_id,
        nombre=row.titulo,
        descripcion=row.descripcion,
        tipo=d.get("tipo", "entrega"),
        orden=row.orden,
        fecha_inicio=row.fecha_inicio,
        fecha_fin=row.fecha_fin,
        estado=row.estado,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def record_to_feature_read(row: ProjectRecord) -> FeatureRead:
    d = _data(row)
    origen_report = d.get("origen_report_id")
    origen_feature = d.get("origen_feature_id")
    return FeatureRead(
        id=row.id,
        milestone_id=row.parent_id,
        project_id=row.project_id,
        nombre=row.titulo,
        descripcion=row.descripcion,
        tipo=d.get("tipo", "desarrollo"),
        prioridad=d.get("prioridad", "media"),
        fecha_inicio=row.fecha_inicio,
        fecha_fin=row.fecha_fin,
        duracion_estimada=d.get("duracion_estimada"),
        estado=row.estado,
        bloqueada=bool(d.get("bloqueada", False)),
        origen_report_id=uuid.UUID(origen_report) if origen_report else None,
        origen_feature_id=uuid.UUID(origen_feature) if origen_feature else None,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def record_to_task_read(row: ProjectRecord, assignee_ids: list[uuid.UUID] | None = None) -> TaskRead:
    d = _data(row)
    parent_task = d.get("parent_task_id")
    return TaskRead(
        id=row.id,
        feature_id=row.parent_id,
        project_id=row.project_id,
        titulo=row.titulo,
        descripcion=row.descripcion,
        estado=row.estado,
        parent_task_id=uuid.UUID(parent_task) if parent_task else None,
        asignado_ids=assignee_ids or [],
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def record_to_query_read(row: ProjectRecord) -> FeatureQueryRead:
    return FeatureQueryRead(
        id=row.id,
        feature_id=row.parent_id,
        titulo=row.titulo,
        descripcion=row.descripcion or "",
        estado=row.estado,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def record_to_report_read(row: ProjectRecord) -> FeatureReportRead:
    d = _data(row)
    reported_by = d.get("reported_by")
    gen_feat = d.get("generated_feature_id")
    return FeatureReportRead(
        id=row.id,
        feature_id=row.parent_id,
        reported_by=uuid.UUID(reported_by) if reported_by else row.created_by,
        tipo=d.get("tipo", "bug"),
        descripcion=row.descripcion or "",
        estado=row.estado,
        generated_feature_id=uuid.UUID(gen_feat) if gen_feat else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
