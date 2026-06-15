"""Repositorio unificado sobre project_records."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Project,
    ProjectRecord,
    ProjectRecordAssignee,
    ProjectRecordDependency,
    ProjectRecordType,
)


def _data(row: ProjectRecord) -> dict[str, Any]:
    raw = row.data
    if isinstance(raw, dict):
        return raw
    return {}


def get_record(db: Session, record_id: uuid.UUID) -> ProjectRecord | None:
    return db.get(ProjectRecord, record_id)


def get_record_or_404(db: Session, record_id: uuid.UUID) -> ProjectRecord:
    row = get_record(db, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    return row


def list_records(
    db: Session,
    project_id: uuid.UUID,
    *,
    entity_type: str | None = None,
    parent_id: uuid.UUID | None = None,
    estado: str | None = None,
) -> list[ProjectRecord]:
    stmt = select(ProjectRecord).where(ProjectRecord.project_id == project_id)
    if entity_type:
        stmt = stmt.where(ProjectRecord.record_type == entity_type)
    if parent_id is not None:
        stmt = stmt.where(ProjectRecord.parent_id == parent_id)
    if estado is not None:
        stmt = stmt.where(ProjectRecord.estado == estado)
    stmt = stmt.order_by(ProjectRecord.orden.asc(), ProjectRecord.created_at.asc())
    return list(db.scalars(stmt))


def list_children(
    db: Session, parent_id: uuid.UUID, entity_type: str | None = None
) -> list[ProjectRecord]:
    stmt = select(ProjectRecord).where(ProjectRecord.parent_id == parent_id)
    if entity_type:
        stmt = stmt.where(ProjectRecord.record_type == entity_type)
    return list(db.scalars(stmt.order_by(ProjectRecord.orden.asc())))


def create_record(
    db: Session,
    project: Project,
    *,
    entity_type: str,
    titulo: str,
    created_by: uuid.UUID,
    parent_id: uuid.UUID | None = None,
    descripcion: str | None = None,
    estado: str | None = None,
    data: dict[str, Any] | None = None,
    fecha_inicio: date | None = None,
    fecha_fin: date | None = None,
    orden: int = 0,
) -> ProjectRecord:
    from app.services.workflow.store import get_active_workflow

    rt = db.scalar(
        select(ProjectRecordType).where(
            ProjectRecordType.project_id == project.id,
            ProjectRecordType.key == entity_type,
        )
    )
    if rt is None:
        raise HTTPException(status_code=422, detail=f"Tipo '{entity_type}' no configurado")

    if parent_id:
        parent = get_record_or_404(db, parent_id)
        if parent.project_id != project.id:
            raise HTTPException(status_code=404, detail="Padre no encontrado")
        parents = rt.parent_types or []
        if parents and parent.record_type not in parents:
            raise HTTPException(status_code=422, detail="Tipo de padre inválido")

    wf = get_active_workflow(db, project.id, entity_type)
    initial = estado or (wf or {}).get("initial_state") or "pendiente"

    row = ProjectRecord(
        id=uuid.uuid4(),
        project_id=project.id,
        record_type=entity_type,
        parent_id=parent_id,
        titulo=titulo.strip(),
        descripcion=descripcion,
        estado=initial,
        data=data or {},
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        orden=orden,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def update_record_fields(
    db: Session,
    row: ProjectRecord,
    *,
    titulo: str | None = None,
    descripcion: str | None = None,
    estado: str | None = None,
    data: dict[str, Any] | None = None,
    fecha_inicio: date | None = None,
    fecha_fin: date | None = None,
    orden: int | None = None,
    merge_data: bool = True,
) -> ProjectRecord:
    if titulo is not None:
        row.titulo = titulo.strip()
    if descripcion is not None:
        row.descripcion = descripcion
    if estado is not None:
        row.estado = estado
    if data is not None:
        if merge_data:
            merged = dict(_data(row))
            merged.update(data)
            row.data = merged
        else:
            row.data = data
    if fecha_inicio is not None:
        row.fecha_inicio = fecha_inicio
    if fecha_fin is not None:
        row.fecha_fin = fecha_fin
    if orden is not None:
        row.orden = orden
    db.flush()
    return row


def get_field(row: ProjectRecord, key: str, default: Any = None) -> Any:
    return _data(row).get(key, default)


def set_field(row: ProjectRecord, key: str, value: Any) -> None:
    d = dict(_data(row))
    d[key] = value
    row.data = d


def sync_assignees(
    db: Session, row: ProjectRecord, user_ids: list[uuid.UUID]
) -> None:
    unique = list(dict.fromkeys(user_ids))
    target = set(unique)
    for a in list(row.assignees):
        if a.user_id not in target:
            db.delete(a)
    existing = {a.user_id for a in row.assignees}
    for uid in unique:
        if uid not in existing:
            db.add(ProjectRecordAssignee(record_id=row.id, user_id=uid))
    db.flush()


def list_assignee_ids(db: Session, row: ProjectRecord) -> list[uuid.UUID]:
    return sorted(a.user_id for a in row.assignees)


def list_dependencies(db: Session, project_id: uuid.UUID) -> list[ProjectRecordDependency]:
    return list(
        db.scalars(
            select(ProjectRecordDependency).where(
                ProjectRecordDependency.project_id == project_id
            )
        )
    )


def milestone_id_for_feature(row: ProjectRecord) -> uuid.UUID | None:
    return row.parent_id


def feature_id_for_child(row: ProjectRecord) -> uuid.UUID | None:
    return row.parent_id


# Legacy attribute shims for workflow/gates compatibility
def as_feature_attrs(row: ProjectRecord) -> dict[str, Any]:
    d = _data(row)
    return {
        "id": row.id,
        "project_id": row.project_id,
        "milestone_id": row.parent_id,
        "nombre": row.titulo,
        "descripcion": row.descripcion,
        "tipo": d.get("tipo", "desarrollo"),
        "prioridad": d.get("prioridad", "media"),
        "fecha_inicio": row.fecha_inicio,
        "fecha_fin": row.fecha_fin,
        "duracion_estimada": d.get("duracion_estimada"),
        "estado": row.estado,
        "bloqueada": bool(d.get("bloqueada", False)),
        "origen_report_id": d.get("origen_report_id"),
        "origen_feature_id": d.get("origen_feature_id"),
        "_record": row,
    }


def as_task_attrs(row: ProjectRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "feature_id": row.parent_id,
        "titulo": row.titulo,
        "descripcion": row.descripcion,
        "estado": row.estado,
        "parent_task_id": _data(row).get("parent_task_id"),
        "_record": row,
    }


def as_milestone_attrs(row: ProjectRecord) -> dict[str, Any]:
    d = _data(row)
    return {
        "id": row.id,
        "project_id": row.project_id,
        "nombre": row.titulo,
        "descripcion": row.descripcion,
        "tipo": d.get("tipo", "entrega"),
        "orden": row.orden,
        "fecha_inicio": row.fecha_inicio,
        "fecha_fin": row.fecha_fin,
        "estado": row.estado,
        "_record": row,
    }


def as_report_attrs(row: ProjectRecord) -> dict[str, Any]:
    d = _data(row)
    return {
        "id": row.id,
        "feature_id": row.parent_id,
        "reported_by": d.get("reported_by"),
        "tipo": d.get("tipo"),
        "descripcion": row.descripcion or "",
        "estado": row.estado,
        "generated_feature_id": d.get("generated_feature_id"),
        "_record": row,
    }


class RecordEntityAdapter:
    """Adapta ProjectRecord para código que espera atributos de entidad legacy."""

    def __init__(self, row: ProjectRecord):
        self._row = row
        self.id = row.id
        self.estado = row.estado
        attrs: dict[str, Any]
        if row.record_type == "feature":
            attrs = as_feature_attrs(row)
            self.nombre = attrs["nombre"]
            self.milestone_id = attrs["milestone_id"]
            self.project_id = attrs["project_id"]
            self.tipo = attrs["tipo"]
            self.bloqueada = attrs["bloqueada"]
            self.feature_id = None
        elif row.record_type == "task":
            attrs = as_task_attrs(row)
            self.titulo = attrs["titulo"]
            self.feature_id = attrs["feature_id"]
            self.project_id = attrs["project_id"]
            self.nombre = attrs["titulo"]
            self.milestone_id = None
            self.tipo = None
            self.bloqueada = False
        elif row.record_type == "milestone":
            attrs = as_milestone_attrs(row)
            self.nombre = attrs["nombre"]
            self.project_id = attrs["project_id"]
            self.milestone_id = None
            self.feature_id = None
            self.tipo = attrs["tipo"]
            self.bloqueada = False
        elif row.record_type == "report":
            attrs = as_report_attrs(row)
            self.feature_id = attrs["feature_id"]
            self.reported_by = attrs["reported_by"]
            self.tipo = attrs["tipo"]
            self.descripcion = attrs["descripcion"]
            self.generated_feature_id = attrs.get("generated_feature_id")
            self.nombre = row.titulo
            self.project_id = row.project_id
            self.milestone_id = None
            self.bloqueada = False
        else:
            self.nombre = row.titulo
            self.project_id = row.project_id
            self.milestone_id = row.parent_id
            self.feature_id = row.parent_id
            self.tipo = _data(row).get("tipo")
            self.bloqueada = bool(_data(row).get("bloqueada", False))

    @property
    def record(self) -> ProjectRecord:
        return self._row
