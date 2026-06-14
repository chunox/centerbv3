"""Seed y consulta de block_catalog y project_blocks."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.blocks.catalog import SYSTEM_BLOCKS
from app.domain.packs.manifest import BlockDef, ViewDef
from app.models.entities import BlockCatalog, Project, ProjectBlock, ProjectView


def ensure_block_catalog(db: Session) -> None:
    for slug, meta in SYSTEM_BLOCKS.items():
        existing = db.get(BlockCatalog, slug)
        if existing:
            continue
        db.add(
            BlockCatalog(
                slug=slug,
                nombre=meta["nombre"],
                descripcion=meta.get("descripcion"),
                manifest=meta.get("manifest", {}),
                orden=meta.get("orden", 0),
            )
        )
    db.flush()


def seed_project_blocks(
    db: Session, project: Project, blocks: list[BlockDef]
) -> dict[str, ProjectBlock]:
    ensure_block_catalog(db)
    created: dict[str, ProjectBlock] = {}
    for block_def in blocks:
        existing = db.scalar(
            select(ProjectBlock.id).where(
                ProjectBlock.project_id == project.id,
                ProjectBlock.key == block_def.key,
            )
        )
        if existing:
            continue
        row = ProjectBlock(
            project_id=project.id,
            block_slug=block_def.block_slug,
            key=block_def.key,
            label=block_def.label,
            config=block_def.config,
            orden=block_def.orden,
        )
        db.add(row)
        db.flush()
        created[block_def.key] = row
    return created


def seed_project_views(
    db: Session, project: Project, views: list[ViewDef]
) -> list[ProjectView]:
    created: list[ProjectView] = []
    for view_def in views:
        existing = db.scalar(
            select(ProjectView.id).where(
                ProjectView.project_id == project.id,
                ProjectView.key == view_def.key,
            )
        )
        if existing:
            continue
        row = ProjectView(
            project_id=project.id,
            key=view_def.key,
            label=view_def.label,
            route=view_def.route,
            icon=view_def.icon,
            section=view_def.section,
            layout=view_def.layout,
            required_capabilities=view_def.required_capabilities,
            orden=view_def.orden,
        )
        db.add(row)
        db.flush()
        created.append(row)
    return created


def list_project_blocks(db: Session, project_id: uuid.UUID) -> list[ProjectBlock]:
    return list(
        db.scalars(
            select(ProjectBlock)
            .where(ProjectBlock.project_id == project_id, ProjectBlock.enabled.is_(True))
            .order_by(ProjectBlock.orden.asc())
        )
    )


def list_project_views(db: Session, project_id: uuid.UUID) -> list[ProjectView]:
    return list(
        db.scalars(
            select(ProjectView)
            .where(ProjectView.project_id == project_id)
            .order_by(ProjectView.orden.asc())
        )
    )


def views_to_workbenches(views: list[ProjectView]) -> list[dict]:
    """Deriva workbenches legacy desde project_views para compat frontend."""
    out: list[dict] = []
    for v in views:
        layout = v.layout or {}
        block_key = None
        blocks = layout.get("blocks") or []
        if blocks:
            block_key = blocks[0].get("project_block_key")
        queue_filter = None
        view_type = "custom"
        entity_type = None
        if block_key:
            pass
        wb: dict = {
            "key": v.key,
            "label": v.label,
            "route": v.route,
            "icon": v.icon,
            "section": v.section,
            "required_capabilities": v.required_capabilities or [],
            "orden": v.orden,
            "view_type": view_type,
            "entity_type": entity_type,
            "queue_filter": queue_filter,
        }
        out.append(wb)
    return out
