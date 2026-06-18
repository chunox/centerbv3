"""
Añade vistas/bloques Scrum nuevos y capacidades PM faltantes en proyectos t6/t7 existentes.

Idempotente — safe re-run.

Uso:
  .venv\\Scripts\\python.exe scripts/sync_scrum_views.py
  .venv\\Scripts\\python.exe scripts/sync_scrum_views.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.capabilities import (
    WORKBENCH_SCRUM_CAPACITY,
    WORKBENCH_SCRUM_IMPEDIMENTS,
    WORKBENCH_SCRUM_METRICS,
    WORKBENCH_SCRUM_REFINEMENT,
)
from app.domain.packs.catalog import get_pack_manifest
from app.domain.packs.manifest import BlockDef, ViewDef
from app.models.entities import Project, ProjectRole, ProjectRoleCapability, ProjectView
from app.services.blocks import ensure_block_catalog, seed_project_blocks, seed_project_views
from app.services.packs import _blocks_from_manifest, _seed_pack_workbenches_from_views

SCRUM_TEMPLATES = frozenset({"t6_scrum_interno", "t7_scrum_cliente"})
PM_EQUIVALENT_SLUGS = frozenset({"pm", "owner", "coordinador"})
SCRUM_PM_CAPS = (
    WORKBENCH_SCRUM_IMPEDIMENTS,
    WORKBENCH_SCRUM_REFINEMENT,
    WORKBENCH_SCRUM_CAPACITY,
    WORKBENCH_SCRUM_METRICS,
)


def _passes_filter(item: BlockDef | ViewDef, template_slug: str) -> bool:
    if item.template_slugs and template_slug not in item.template_slugs:
        return False
    if item.exclude_template_slugs and template_slug in item.exclude_template_slugs:
        return False
    return True


def _is_scrum_project(db, project: Project) -> bool:
    if project.template_slug in SCRUM_TEMPLATES:
        return True
    return bool(
        db.scalar(
            select(ProjectView.id).where(
                ProjectView.project_id == project.id,
                ProjectView.key == "product_backlog",
            )
        )
    )


def _ensure_pm_scrum_capabilities(db, *, dry_run: bool) -> int:
    added = 0
    roles = list(db.scalars(select(ProjectRole).where(ProjectRole.slug.in_(PM_EQUIVALENT_SLUGS))))
    for role in roles:
        for cap in SCRUM_PM_CAPS:
            exists = db.scalar(
                select(ProjectRoleCapability.id).where(
                    ProjectRoleCapability.role_id == role.id,
                    ProjectRoleCapability.capability_key == cap,
                )
            )
            if exists:
                continue
            print(f"[cap] +{cap} → rol {role.slug} (proyecto {role.project_id})")
            if not dry_run:
                db.add(ProjectRoleCapability(role_id=role.id, capability_key=cap))
            added += 1
    return added


def _sync_scrum_layout(db, project: Project, *, dry_run: bool) -> tuple[int, int]:
    manifest = get_pack_manifest(project.pack_slug or "software")
    if manifest is None or not manifest.project_views:
        return 0, 0

    template_slug = project.template_slug or "default"
    block_defs = [b for b in _blocks_from_manifest(manifest) if _passes_filter(b, template_slug)]
    view_defs = [v for v in manifest.project_views if _passes_filter(v, template_slug)]

    scrum_view_keys = {
        "product_backlog",
        "sprint_planning",
        "sprint_board",
        "scrum_metrics",
        "scrum_refinement",
        "scrum_capacity",
        "scrum_impediments",
        "scrum_daily",
        "scrum_planning_poker",
        "scrum_sprint_review",
        "scrum_retro",
    }
    scrum_blocks = [b for b in block_defs if b.key in scrum_view_keys]
    scrum_views = [v for v in view_defs if v.key in scrum_view_keys]

    before_keys = set(
        db.scalars(
            select(ProjectView.key).where(ProjectView.project_id == project.id)
        )
    )
    if dry_run:
        new_views = [v.key for v in scrum_views if v.key not in before_keys]
        if new_views:
            print(f"[view] +{', '.join(new_views)} → {project.nombre}")
        return len(new_views), 0

    ensure_block_catalog(db)
    seed_project_blocks(db, project, scrum_blocks)
    seed_project_views(db, project, scrum_views)
    _seed_pack_workbenches_from_views(db, project)

    after_keys = set(
        db.scalars(
            select(ProjectView.key).where(ProjectView.project_id == project.id)
        )
    )
    added = len(after_keys - before_keys)
    if added:
        print(f"[view] +{added} vistas Scrum → {project.nombre}")
    return added, 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Solo listar cambios")
    args = parser.parse_args()
    dry_run = args.dry_run

    caps_added = 0
    views_added = 0
    projects_synced = 0

    with SessionLocal() as db:
        projects = list(db.scalars(select(Project).where(Project.estado == "activo")))
        scrum_projects = [p for p in projects if _is_scrum_project(db, p)]

        caps_added = _ensure_pm_scrum_capabilities(db, dry_run=dry_run)
        for project in scrum_projects:
            added, synced = _sync_scrum_layout(db, project, dry_run=dry_run)
            views_added += added
            projects_synced += synced

        if not dry_run:
            db.commit()

    mode = " (dry-run)" if dry_run else ""
    print(f"[scrum-sync] Proyectos Scrum: {len(scrum_projects)}{mode}")
    print(f"[scrum-sync] Capacidades añadidas: {caps_added}{mode}")
    print(f"[scrum-sync] Vistas añadidas: {views_added}{mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
