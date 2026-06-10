from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.schemas.hub_entries import HubEntryCreate, HubEntryRead, HubEntryUpdate
from app.services.access import assert_member_of_project, hub_entry_visible_for_user
from app.services.hub_entries import (
    create_hub_entry,
    delete_hub_entry,
    enrich_hub_entries_with_authors,
    get_hub_entry_or_404,
    list_hub_entries,
    update_hub_entry,
)

router = APIRouter(tags=["hub-entries"])


@router.get("/{project_id}/hub-entries", response_model=list[HubEntryRead])
def list_project_hub_entries(
    project_id: UUID,
    viewer_user_id: UUID | None = Query(default=None),
    tipo: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    if viewer_user_id is not None:
        assert_member_of_project(db, project.id, viewer_user_id)

    tipo_filter = None
    if tipo in ("update", "note"):
        tipo_filter = tipo  # type: ignore[assignment]

    entries = list_hub_entries(
        db,
        project.id,
        viewer_user_id=viewer_user_id,
        tipo=tipo_filter,
        limit=limit,
        offset=offset,
    )
    return enrich_hub_entries_with_authors(db, entries)


@router.post("/{project_id}/hub-entries", response_model=HubEntryRead, status_code=201)
def create_project_hub_entry(
    project_id: UUID,
    payload: HubEntryCreate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    entry = create_hub_entry(db, project, payload)
    db.commit()
    db.refresh(entry)
    enriched = enrich_hub_entries_with_authors(db, [entry])
    return enriched[0]


@router.patch("/{project_id}/hub-entries/{entry_id}", response_model=HubEntryRead)
def patch_project_hub_entry(
    project_id: UUID,
    entry_id: UUID,
    payload: HubEntryUpdate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    entry = get_hub_entry_or_404(db, project_id, entry_id)
    update_hub_entry(db, entry, project, payload)
    db.commit()
    db.refresh(entry)
    enriched = enrich_hub_entries_with_authors(db, [entry])
    return enriched[0]


@router.delete("/{project_id}/hub-entries/{entry_id}", status_code=204)
def remove_project_hub_entry(
    project_id: UUID,
    entry_id: UUID,
    actor_user_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    entry = get_hub_entry_or_404(db, project_id, entry_id)
    delete_hub_entry(db, entry, project, actor_user_id=actor_user_id)
    db.commit()


@router.get("/{project_id}/hub-entries/{entry_id}", response_model=HubEntryRead)
def get_project_hub_entry(
    project_id: UUID,
    entry_id: UUID,
    viewer_user_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    if viewer_user_id is not None:
        assert_member_of_project(db, project.id, viewer_user_id)
    entry = get_hub_entry_or_404(db, project_id, entry_id)
    if not hub_entry_visible_for_user(
        db, entry, viewer_user_id=viewer_user_id
    ):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver esta entrada")
    enriched = enrich_hub_entries_with_authors(db, [entry])
    return enriched[0]
