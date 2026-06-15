from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

DocumentExposureAmbito = Literal["proyecto", "milestone", "feature", "record"]


class DocumentExposureCreate(BaseModel):
    ambito: DocumentExposureAmbito
    record_id: UUID | None = None
    document_id: UUID | None = None
    attachment_id: UUID | None = None
    hub_entry_id: UUID | None = None
    titulo_visible: str | None = Field(default=None, max_length=255)
    expuesto_por: UUID

    @model_validator(mode="after")
    def validar_target_y_ambito(self) -> DocumentExposureCreate:
        targets = [
            self.document_id is not None,
            self.attachment_id is not None,
            self.hub_entry_id is not None,
        ]
        if sum(targets) != 1:
            raise ValueError(
                "Debe indicar exactamente uno de document_id, attachment_id o hub_entry_id"
            )
        if self.ambito == "proyecto" and self.record_id is not None:
            raise ValueError("ambito 'proyecto' no admite record_id")
        if self.ambito != "proyecto" and self.record_id is None:
            raise ValueError(f"ambito '{self.ambito}' requiere record_id")
        return self


class DocumentExposureUpdate(BaseModel):
    actor_user_id: UUID
    titulo_visible: str | None = Field(default=None, max_length=255)


class DocumentExposureRead(BaseModel):
    id: UUID
    project_id: UUID
    ambito: DocumentExposureAmbito
    record_id: UUID | None
    document_id: UUID | None
    attachment_id: UUID | None
    hub_entry_id: UUID | None
    titulo_visible: str | None
    expuesto_por: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
