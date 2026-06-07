from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

FeatureTransitionTipoProyecto = Literal["con_cliente", "interno", "ambos"]
TransitionRol = Literal["cliente", "pm", "dev", "qa"]
TaskTransitionRol = Literal["dev", "pm"]


class FeatureStateTransitionRead(BaseModel):
    id: UUID
    tipo_proyecto: FeatureTransitionTipoProyecto
    estado_desde: str
    estado_hasta: str
    rol_permitido: TransitionRol
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskStateTransitionRead(BaseModel):
    id: UUID
    estado_desde: str
    estado_hasta: str
    rol_permitido: TaskTransitionRol
    created_at: datetime

    model_config = {"from_attributes": True}
