"""Schemas de respuesta para GET /projects/{id}/access-context."""
from pydantic import BaseModel


class StateInfoSchema(BaseModel):
    key: str
    label: str
    category: str   # pending | active | done | terminal


class TransitionInfoSchema(BaseModel):
    action_id: str
    label: str
    from_states: list[str]
    to_state: str
    required_roles: list[str] = []
    required_capability: str | None = None


class WorkflowInfoSchema(BaseModel):
    entity_type: str
    states: list[StateInfoSchema]
    transitions: list[TransitionInfoSchema]


class FieldInfoSchema(BaseModel):
    key: str
    label: str
    type: str


class EntityTypeInfoSchema(BaseModel):
    label: str
    states: list[StateInfoSchema]
    fields: list[FieldInfoSchema]


class WorkbenchInfoSchema(BaseModel):
    key: str
    label: str
    route: str
    icon: str
    section: str
    order: int
    custom_view_key: str


class ProjectInfoSchema(BaseModel):
    id: str
    nombre: str
    delivery_mode: str
    effort_unit: str
    hours_per_story_point: float


class AccessContextResponse(BaseModel):
    capabilities: list[str]
    workbenches: list[WorkbenchInfoSchema]
    entity_types: dict[str, EntityTypeInfoSchema]
    workflows: dict[str, WorkflowInfoSchema]
    project: ProjectInfoSchema
    role_slug: str | None = None
    role_slugs: list[str] = []
