"""API genérica de registros de proyecto."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.domain.capabilities import PROJECT_ROLES_MANAGE, is_record_capability
from app.models.entities import ProjectRecord, ProjectRecordDependency
from app.schemas.records import (
    RecordCreate,
    RecordDependencyCreate,
    RecordDependencyRead,
    RecordRead,
    RecordTransitionRead,
    RecordTransitionRequest,
    RecordUpdate,
)
from app.services.records import generic_store, registry
from app.services.workflow.authorize import assert_capability
from app.services.workflow.engine import get_available_transitions

router = APIRouter(prefix="/projects", tags=["project-records"])


def _dto_to_read(dto) -> RecordRead:
    return RecordRead(
        id=dto.id,
        project_id=dto.project_id,
        record_type=dto.record_type,
        storage=dto.storage,
        titulo=dto.titulo,
        descripcion=dto.descripcion,
        estado=dto.estado,
        parent_id=dto.parent_id,
        data=dto.data,
        fecha_inicio=dto.fecha_inicio,
        fecha_fin=dto.fecha_fin,
        orden=dto.orden,
        assignee_ids=dto.assignee_ids,
        created_by=dto.created_by,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def _assert_record_cap(db: Session, project_id: UUID, user_id: UUID, cap: str) -> None:
    from app.services.workflow.capabilities import user_has_capability

    if user_has_capability(db, project_id, user_id, cap):
        return
    if user_has_capability(db, project_id, user_id, PROJECT_ROLES_MANAGE):
        return
    assert_capability(db, project_id, user_id, cap)


@router.get("/{project_id}/records", response_model=list[RecordRead])
def list_project_records(
    project_id: UUID,
    record_type: str = Query(...),
    parent_id: UUID | None = None,
    actor_user_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    _assert_record_cap(
        db, project.id, actor_user_id, f"record.{record_type}.read"
    )
    rows = registry.list_records(
        db, project.id, record_type=record_type, parent_id=parent_id
    )
    return [_dto_to_read(r) for r in rows]


@router.post("/{project_id}/records", response_model=RecordRead, status_code=201)
def create_project_record(
    project_id: UUID,
    payload: RecordCreate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    _assert_record_cap(
        db, project.id, payload.actor_user_id, f"record.{payload.record_type}.create"
    )
    if registry.is_legacy(payload.record_type):
        raise HTTPException(
            status_code=422,
            detail=f"Tipo '{payload.record_type}' usa API legacy",
        )
    dto = generic_store.create_record(
        db,
        project,
        record_type=payload.record_type,
        titulo=payload.titulo,
        created_by=payload.actor_user_id,
        descripcion=payload.descripcion,
        parent_id=payload.parent_id,
        data=payload.data,
        fecha_inicio=payload.fecha_inicio,
        fecha_fin=payload.fecha_fin,
        assignee_ids=payload.assignee_ids,
        initial_state=payload.initial_state,
    )
    db.commit()
    return _dto_to_read(dto)


@router.get("/{project_id}/records/{record_id}", response_model=RecordRead)
def get_project_record(
    project_id: UUID,
    record_id: UUID,
    actor_user_id: UUID = Query(...),
    record_type: str | None = None,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    ref = registry.resolve_ref(db, record_type or "", record_id) if record_type else None
    if ref is None:
        row = db.get(ProjectRecord, record_id)
        if row and row.project_id == project.id:
            ref = registry.resolve_ref(db, row.record_type, record_id)
    if ref is None:
        for rt in registry.workflow_entity_types_for_project(db, project.id):
            ref = registry.resolve_ref(db, rt, record_id)
            if ref:
                break
    if ref is None or ref.project_id != project.id:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    _assert_record_cap(db, project.id, actor_user_id, f"record.{ref.record_type}.read")
    dto, _ = registry.get(db, ref)
    if dto is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    return _dto_to_read(dto)


@router.patch("/{project_id}/records/{record_id}", response_model=RecordRead)
def update_project_record(
    project_id: UUID,
    record_id: UUID,
    payload: RecordUpdate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    row = db.get(ProjectRecord, record_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    _assert_record_cap(
        db, project.id, payload.actor_user_id, f"record.{row.record_type}.edit"
    )
    dto = generic_store.update_record(
        db,
        row,
        titulo=payload.titulo,
        descripcion=payload.descripcion,
        data=payload.data,
        fecha_inicio=payload.fecha_inicio,
        fecha_fin=payload.fecha_fin,
        orden=payload.orden,
    )
    if payload.assignee_ids is not None:
        generic_store.sync_assignees(db, row, payload.assignee_ids)
        dto = generic_store.get_record(db, row.id) or dto
    db.commit()
    return _dto_to_read(dto)


@router.delete("/{project_id}/records/{record_id}", status_code=204)
def delete_project_record(
    project_id: UUID,
    record_id: UUID,
    actor_user_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    row = db.get(ProjectRecord, record_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    cap = f"record.{row.record_type}.delete"
    if not is_record_capability(cap):
        cap = f"record.{row.record_type}.edit"
    _assert_record_cap(db, project.id, actor_user_id, cap)
    generic_store.delete_record(db, row)
    db.commit()


@router.post("/{project_id}/records/{record_id}/transition", response_model=RecordRead)
def transition_project_record(
    project_id: UUID,
    record_id: UUID,
    payload: RecordTransitionRequest,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    row = db.get(ProjectRecord, record_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    dto = generic_store.transition_record(
        db,
        project,
        row,
        action_id=payload.action_id,
        actor_user_id=payload.actor_user_id,
        target_state=payload.target_state,
        form_data=payload.form_data,
    )
    db.commit()
    return _dto_to_read(dto)


@router.get(
    "/{project_id}/records/{record_id}/transitions",
    response_model=list[RecordTransitionRead],
)
def list_record_transitions(
    project_id: UUID,
    record_id: UUID,
    actor_user_id: UUID = Query(...),
    record_type: str | None = None,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    entity = None
    etype = record_type
    row = db.get(ProjectRecord, record_id)
    if row and row.project_id == project.id:
        entity = row
        etype = row.record_type
    else:
        for rt in registry.workflow_entity_types_for_project(db, project.id):
            adapter = registry.get_adapter(rt)
            if adapter:
                entity = adapter.get_entity(db, record_id)
                if entity is not None:
                    etype = rt
                    break
    if entity is None or etype is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    available = get_available_transitions(
        db, project, entity, entity_type=etype, user_id=actor_user_id
    )
    return [RecordTransitionRead(**t) for t in available]


@router.get(
    "/{project_id}/record-dependencies",
    response_model=list[RecordDependencyRead],
)
def list_record_dependencies(
    project_id: UUID,
    actor_user_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, PROJECT_ROLES_MANAGE)
    deps = generic_store.list_dependencies(db, project.id)
    return [RecordDependencyRead.model_validate(d) for d in deps]


@router.post(
    "/{project_id}/record-dependencies",
    response_model=RecordDependencyRead,
    status_code=201,
)
def create_record_dependency(
    project_id: UUID,
    payload: RecordDependencyCreate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, payload.actor_user_id, PROJECT_ROLES_MANAGE)
    dep = generic_store.add_dependency(
        db,
        project,
        predecessor_id=payload.predecessor_id,
        successor_id=payload.successor_id,
        dependency_type=payload.dependency_type,
    )
    db.commit()
    return RecordDependencyRead.model_validate(dep)


@router.delete("/{project_id}/record-dependencies/{dep_id}", status_code=204)
def delete_record_dependency(
    project_id: UUID,
    dep_id: UUID,
    actor_user_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, PROJECT_ROLES_MANAGE)
    dep = db.get(ProjectRecordDependency, dep_id)
    if dep is None or dep.project_id != project.id:
        raise HTTPException(status_code=404, detail="Dependencia no encontrada")
    generic_store.remove_dependency(db, dep)
    db.commit()
