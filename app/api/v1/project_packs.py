"""Catálogo de project packs."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth_deps import get_current_actor_id
from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.domain.capabilities import PROJECT_ROLES_MANAGE
from app.domain.packs.manifest import PackManifest
from app.models.entities import ProjectPack
from app.schemas.packs import PackContextRead, PackSummaryRead, PackViewRead
from app.services.packs import ensure_system_packs, get_project_pack_manifest, seed_project_from_pack
from app.services.workflow.authorize import assert_capability

router = APIRouter(prefix="/project-packs", tags=["project-packs"])


@router.get("", response_model=list[PackSummaryRead])
def list_packs(db: Session = Depends(get_db)):
    ensure_system_packs(db)
    db.commit()
    rows = list(
        db.scalars(select(ProjectPack).order_by(ProjectPack.orden.asc(), ProjectPack.nombre))
    )
    return [
        PackSummaryRead(
            slug=r.slug,
            nombre=r.nombre,
            descripcion=r.descripcion or "",
            orden=r.orden,
        )
        for r in rows
    ]


@router.get("/{slug}", response_model=PackContextRead)
def get_pack(slug: str, db: Session = Depends(get_db)):
    ensure_system_packs(db)
    row = db.scalar(select(ProjectPack).where(ProjectPack.slug == slug))
    if row is None:
        raise HTTPException(status_code=404, detail="Pack no encontrado")
    manifest = PackManifest.model_validate_json(row.manifest)
    return PackContextRead(
        slug=manifest.slug,
        nombre=manifest.nombre,
        descripcion=manifest.descripcion,
        entity_types=[et.model_dump() for et in manifest.entity_types],
        views=[
            PackViewRead(
                key=v.key,
                type=v.type,
                label=v.label,
                entity_type=v.entity_type,
                entity_types=v.entity_types,
                workbench_key=v.workbench_key,
            )
            for v in manifest.views
        ],
    )


@router.post("/projects/{project_id}/apply/{pack_slug}", status_code=204)
def apply_pack_to_project(
    project_id: UUID,
    pack_slug: str,
    template_slug: str | None = None,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, PROJECT_ROLES_MANAGE)
    seed_project_from_pack(db, project, pack_slug, template_slug=template_slug)
    db.commit()
