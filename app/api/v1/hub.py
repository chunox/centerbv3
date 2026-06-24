"""
Hub entries — notas, decisiones, riesgos y documentos del proyecto.
GET  /projects/{id}/hub?page=&per_page=
POST /projects/{id}/hub
PATCH /projects/{id}/hub/{entry_id}
DELETE /projects/{id}/hub/{entry_id}
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_actor_id
from app.api.v1.projects import get_project_or_404
from app.database import get_db
from app.models.entities import HubEntry
from app.services.access import require_project_member

router = APIRouter()

VALID_TIPOS = {"nota", "decision", "riesgo", "documento"}


# ─── Schemas ──────────────────────────────────────────────────────────────────

class HubEntryResponse(BaseModel):
    id: str
    project_id: str
    author_id: str
    tipo: str
    titulo: str
    contenido: str | None = None
    record_id: str | None = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class CreateHubEntryRequest(BaseModel):
    tipo: str
    titulo: str
    contenido: str | None = None
    record_id: str | None = None


class UpdateHubEntryRequest(BaseModel):
    titulo: str | None = None
    contenido: str | None = None
    tipo: str | None = None


def _to_response(e: HubEntry) -> HubEntryResponse:
    return HubEntryResponse(
        id=e.id,
        project_id=e.project_id,
        author_id=e.author_id,
        tipo=e.tipo,
        titulo=e.titulo,
        contenido=e.contenido,
        record_id=e.record_id,
        created_at=e.created_at.isoformat(),
        updated_at=e.updated_at.isoformat(),
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{project_id}/hub", response_model=dict)
def list_hub_entries(
    project_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    tipo: str | None = Query(None),
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    q = db.query(HubEntry).filter(HubEntry.project_id == str(project_id))
    if tipo:
        q = q.filter(HubEntry.tipo == tipo)
    total = q.count()
    entries = q.order_by(HubEntry.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": [_to_response(e) for e in entries],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.post("/{project_id}/hub", response_model=HubEntryResponse, status_code=status.HTTP_201_CREATED)
def create_hub_entry(
    project_id: str,
    body: CreateHubEntryRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    if body.tipo not in VALID_TIPOS:
        raise HTTPException(status_code=422, detail=f"tipo inválido. Valores: {sorted(VALID_TIPOS)}")
    entry = HubEntry(
        project_id=str(project_id),
        author_id=actor_id,
        tipo=body.tipo,
        titulo=body.titulo,
        contenido=body.contenido,
        record_id=body.record_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _to_response(entry)


@router.patch("/{project_id}/hub/{entry_id}", response_model=HubEntryResponse)
def update_hub_entry(
    project_id: str,
    entry_id: str,
    body: UpdateHubEntryRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    entry = db.query(HubEntry).filter(
        HubEntry.id == str(entry_id),
        HubEntry.project_id == str(project_id),
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada de Hub no encontrada")
    is_author = entry.author_id == actor_id
    is_pm = ctx.role_slug == "pm"
    if not (is_author or is_pm):
        raise HTTPException(status_code=403, detail="Sin permiso para editar esta entrada")
    if body.titulo is not None:
        entry.titulo = body.titulo
    if body.contenido is not None:
        entry.contenido = body.contenido
    if body.tipo is not None:
        if body.tipo not in VALID_TIPOS:
            raise HTTPException(status_code=422, detail=f"tipo inválido. Valores: {sorted(VALID_TIPOS)}")
        entry.tipo = body.tipo
    db.commit()
    db.refresh(entry)
    return _to_response(entry)


@router.delete("/{project_id}/hub/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hub_entry(
    project_id: str,
    entry_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    entry = db.query(HubEntry).filter(
        HubEntry.id == str(entry_id),
        HubEntry.project_id == str(project_id),
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada de Hub no encontrada")
    is_author = entry.author_id == actor_id
    is_pm = ctx.role_slug == "pm"
    if not (is_author or is_pm):
        raise HTTPException(status_code=403, detail="Sin permiso para eliminar esta entrada")
    db.delete(entry)
    db.commit()
