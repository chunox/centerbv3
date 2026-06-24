from datetime import date, datetime

from pydantic import BaseModel


class ProjectResponse(BaseModel):
    id: str
    org_id: str
    name: str
    description: str | None = None
    pack_slug: str | None = None
    template_slug: str | None = None
    delivery_mode: str | None = None
    estado: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
