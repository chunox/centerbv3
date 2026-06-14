"""
Añade workbench/bloque Equipo y capacidad workbench.team a roles PM en proyectos existentes.

Idempotente — safe re-run.

Uso:
  .venv\\Scripts\\python.exe scripts/add_team_workbench.py
  .venv\\Scripts\\python.exe scripts/add_team_workbench.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.capabilities import WORKBENCH_TEAM
from app.domain.packs.manifest import BlockDef, ViewDef
from app.models.entities import Project, ProjectRole, ProjectRoleCapability, ProjectView
from app.services.blocks import ensure_block_catalog, seed_project_blocks, seed_project_views
from app.services.packs import _seed_pack_workbenches_from_views

PM_EQUIVALENT_SLUGS = frozenset({"pm", "owner", "coordinador"})

TEAM_BLOCK = BlockDef(
    key="team",
    block_slug="team",
    label="Equipo",
    config={"view_type": "team"},
    orden=25,
)

TEAM_VIEW = ViewDef(
    key="team",
    label="Equipo",
    route="team",
    icon="users",
    section="pm",
    layout={"blocks": [{"project_block_key": "team", "width": "full"}]},
    required_capabilities=[WORKBENCH_TEAM],
    orden=25,
    view_type="team",
)


def _ensure_pm_team_capability(db, *, dry_run: bool) -> int:
    added = 0
    roles = list(db.scalars(select(ProjectRole).where(ProjectRole.slug.in_(PM_EQUIVALENT_SLUGS))))
    for role in roles:
        exists = db.scalar(
            select(ProjectRoleCapability.id).where(
                ProjectRoleCapability.role_id == role.id,
                ProjectRoleCapability.capability_key == WORKBENCH_TEAM,
            )
        )
        if exists:
            continue
        print(f"[cap] +{WORKBENCH_TEAM} → rol {role.slug} ({role.project_id})")
        if not dry_run:
            db.add(
                ProjectRoleCapability(
                    role_id=role.id,
                    capability_key=WORKBENCH_TEAM,
                )
            )
        added += 1
    return added


def _ensure_team_view(db, project: Project, *, dry_run: bool) -> bool:
    existing = db.scalar(
        select(ProjectView.id).where(
            ProjectView.project_id == project.id,
            ProjectView.key == "team",
        )
    )
    if existing:
        return False
    print(f"[view] +team → {project.nombre} ({project.pack_slug})")
    if not dry_run:
        seed_project_blocks(db, project, [TEAM_BLOCK])
        seed_project_views(db, project, [TEAM_VIEW])
        _seed_pack_workbenches_from_views(db, project)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Solo listar cambios")
    args = parser.parse_args()
    dry_run = args.dry_run

    with SessionLocal() as db:
        if not dry_run:
            ensure_block_catalog(db)
            db.commit()

        caps_added = _ensure_pm_team_capability(db, dry_run=dry_run)
        views_added = 0
        projects = list(db.scalars(select(Project).where(Project.estado == "activo")))
        for project in projects:
            if _ensure_team_view(db, project, dry_run=dry_run):
                views_added += 1

        if not dry_run:
            db.commit()

    mode = " (dry-run)" if dry_run else ""
    print(f"[team] Capacidades añadidas: {caps_added}{mode}")
    print(f"[team] Vistas añadidas: {views_added}{mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
