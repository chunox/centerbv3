"""
Endpoint para obtener las organizaciones del usuario actual.
Usado por el frontend en el dashboard inicial.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api.v1.deps import get_current_actor_id
from app.database import get_db
from app.models.entities import Organization, OrganizationMember

router = APIRouter()


class OrgResponse(BaseModel):
    id: str
    nombre: str
    slug: str
    estado: str


@router.get("/my-orgs", response_model=list[OrgResponse])
def my_orgs(
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """Devuelve las organizaciones a las que pertenece el actor."""
    orgs = (
        db.query(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .filter(OrganizationMember.user_id == actor_id)
        .order_by(Organization.nombre)
        .all()
    )
    return [
        OrgResponse(id=str(o.id), nombre=o.nombre, slug=o.slug, estado=o.estado)
        for o in orgs
    ]
