"""CRUD de personalización de espacio (entity types, fields, blocks, views)."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.domain.capabilities import PROJECT_SETTINGS_EDIT
from app.models.entities import (
    ProjectFieldDefinition,
    ProjectRecordType,
    ProjectView,
)
from app.schemas.access_context import (
    EntityTypeRead,
    FieldDefinitionRead,
    ProjectViewRead,
)
from app.schemas.project_structure import EntityTypeCreate, EntityTypeDelete
from app.services.blocks import list_project_views
from app.services.packs import list_field_definitions, list_record_types
from app.services.project_structure import (
    add_entity_type_to_project,
    delete_entity_type_from_project,
    update_entity_type_on_project,
)
from app.services.workflow.authorize import assert_capability

router = APIRouter(prefix="/projects", tags=["project-customization"])


class EntityTypeUpdate(BaseModel):
    actor_user_id: UUID
    label: str | None = None
    icon: str | None = None
    traits: dict | None = None
    parent_type_keys: list[str] | None = None
    field_schema: list[dict] | None = None
    orden: int | None = None


class FieldDefinitionCreate(BaseModel):
    actor_user_id: UUID
    entity_type_key: str
    field_key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=120)
    field_type: str = "text"
    config: dict = Field(default_factory=dict)
    orden: int = 0


class ViewCreate(BaseModel):
    actor_user_id: UUID
    key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=120)
    route: str
    icon: str = "circle"
    section: str = "plan"
    layout: dict = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=list)
    orden: int = 0


@router.get("/{project_id}/entity-types", response_model=list[EntityTypeRead])
def list_entity_types(project_id: UUID, db: Session = Depends(get_db)):
    project = get_project_or_404(project_id, db)
    import json

    result: list[EntityTypeRead] = []
    for rt in list_record_types(db, project.id):
        try:
            fields = json.loads(rt.field_schema) if rt.field_schema else []
        except json.JSONDecodeError:
            fields = []
        try:
            parents = json.loads(rt.parent_types) if rt.parent_types else []
        except json.JSONDecodeError:
            parents = []
        result.append(
            EntityTypeRead(
                key=rt.key,
                label=rt.label,
                storage=rt.storage,
                field_schema=fields,
                parent_types=parents,
                icon=rt.icon,
                traits=rt.traits or {},
                is_system=rt.is_system,
                orden=rt.orden,
            )
        )
    return result


def _entity_type_to_read(rt: ProjectRecordType) -> EntityTypeRead:
    try:
        fields = json.loads(rt.field_schema) if rt.field_schema else []
    except json.JSONDecodeError:
        fields = []
    try:
        parents = json.loads(rt.parent_types) if rt.parent_types else []
    except json.JSONDecodeError:
        parents = []
    return EntityTypeRead(
        key=rt.key,
        label=rt.label,
        storage=rt.storage,
        field_schema=fields,
        parent_types=parents,
        icon=rt.icon,
        traits=rt.traits or {},
        is_system=rt.is_system,
        orden=rt.orden,
    )


@router.post("/{project_id}/entity-types", response_model=EntityTypeRead, status_code=201)
def create_entity_type(
    project_id: UUID,
    payload: EntityTypeCreate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, payload.actor_user_id, PROJECT_SETTINGS_EDIT)
    existing = db.scalar(
        select(ProjectRecordType.id).where(
            ProjectRecordType.project_id == project.id,
            ProjectRecordType.key == payload.key,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Entity type ya existe")
    from app.schemas.project_structure import ProjectStructureEntity

    entity = ProjectStructureEntity(
        key=payload.key,
        label=payload.label,
        parent_type_keys=payload.parent_type_keys,
        icon=payload.icon,
        traits=payload.traits,
        fields=payload.fields,
        workflow=payload.workflow,
        orden=payload.orden,
    )
    try:
        row = add_entity_type_to_project(db, project, entity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return _entity_type_to_read(row)


@router.patch("/{project_id}/entity-types/{key}", response_model=EntityTypeRead)
def update_entity_type(
    project_id: UUID,
    key: str,
    payload: EntityTypeUpdate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, payload.actor_user_id, PROJECT_SETTINGS_EDIT)
    try:
        row = update_entity_type_on_project(
            db,
            project,
            key,
            label=payload.label,
            icon=payload.icon,
            traits=payload.traits,
            parent_type_keys=payload.parent_type_keys,
            field_schema=payload.field_schema,
            orden=payload.orden,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return _entity_type_to_read(row)


@router.delete("/{project_id}/entity-types/{key}")
def delete_entity_type(
    project_id: UUID,
    key: str,
    payload: EntityTypeDelete,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, payload.actor_user_id, PROJECT_SETTINGS_EDIT)
    delete_entity_type_from_project(db, project, key)
    db.commit()
    return {"ok": True}


@router.get("/{project_id}/field-definitions", response_model=list[FieldDefinitionRead])
def list_field_defs(project_id: UUID, db: Session = Depends(get_db)):
    project = get_project_or_404(project_id, db)
    return [
        FieldDefinitionRead(
            entity_type_key=fd.entity_type_key,
            field_key=fd.field_key,
            label=fd.label,
            field_type=fd.field_type,
            config=fd.config or {},
            orden=fd.orden,
            is_system=fd.is_system,
        )
        for fd in list_field_definitions(db, project.id)
    ]


@router.post("/{project_id}/field-definitions", response_model=FieldDefinitionRead, status_code=201)
def create_field_def(
    project_id: UUID,
    payload: FieldDefinitionCreate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, payload.actor_user_id, PROJECT_SETTINGS_EDIT)
    existing = db.scalar(
        select(ProjectFieldDefinition.id).where(
            ProjectFieldDefinition.project_id == project.id,
            ProjectFieldDefinition.entity_type_key == payload.entity_type_key,
            ProjectFieldDefinition.field_key == payload.field_key,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Campo ya existe")
    row = ProjectFieldDefinition(
        project_id=project.id,
        entity_type_key=payload.entity_type_key,
        field_key=payload.field_key,
        label=payload.label,
        field_type=payload.field_type,
        config=payload.config,
        orden=payload.orden,
        is_system=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return FieldDefinitionRead(
        entity_type_key=row.entity_type_key,
        field_key=row.field_key,
        label=row.label,
        field_type=row.field_type,
        config=row.config or {},
        orden=row.orden,
        is_system=row.is_system,
    )


@router.get("/{project_id}/views", response_model=list[ProjectViewRead])
def list_views(project_id: UUID, db: Session = Depends(get_db)):
    project = get_project_or_404(project_id, db)
    return [
        ProjectViewRead(
            key=v.key,
            label=v.label,
            route=v.route,
            icon=v.icon,
            section=v.section,
            layout=v.layout or {},
            required_capabilities=v.required_capabilities or [],
            orden=v.orden,
        )
        for v in list_project_views(db, project.id)
    ]
