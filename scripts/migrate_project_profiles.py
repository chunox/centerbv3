"""
Verifica y corrige profile_slug en proyectos existentes (idempotente).

Deriva el perfil esperado desde template_slug (software) o default (packs genéricos).
No re-seedea workflows custom (version > 1).

Uso:
  .venv\\Scripts\\python.exe scripts/migrate_project_profiles.py
  .venv\\Scripts\\python.exe scripts/migrate_project_profiles.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.project_profiles import PROFILE_DEFAULT
from app.domain.project_templates import get_template
from app.models.entities import Project, ProjectWorkflowDefinition


def _target_profile(project: Project) -> str:
    pack = project.pack_slug or "software"
    if pack != "software":
        return PROFILE_DEFAULT
    try:
        return get_template(project.template_slug).profile_slug
    except KeyError:
        return getattr(project, "profile_slug", None) or PROFILE_DEFAULT


def migrate(*, dry_run: bool = False) -> int:
    db_path = ROOT / "data" / "v3.db"
    if not db_path.exists():
        print(f"[migrate] No existe {db_path}")
        return 1

    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    updated = 0

    with SessionLocal() as db:
        projects = list(db.scalars(select(Project)))
        for project in projects:
            target = _target_profile(project)
            current = getattr(project, "profile_slug", None) or PROFILE_DEFAULT
            if current == target:
                continue
            custom_wf = db.scalar(
                select(ProjectWorkflowDefinition.id)
                .where(
                    ProjectWorkflowDefinition.project_id == project.id,
                    ProjectWorkflowDefinition.version > 1,
                )
                .limit(1)
            )
            note = " (workflows custom, solo profile)" if custom_wf else ""
            print(
                f"[migrate] {project.nombre} ({project.id}): "
                f"profile {current} -> {target}{note}"
            )
            if not dry_run:
                project.profile_slug = target
                updated += 1
        if not dry_run:
            db.commit()

    print(f"[migrate] {'(dry-run) ' if dry_run else ''}Proyectos actualizados: {updated}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrar profile_slug en proyectos")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar cambios")
    args = parser.parse_args()
    return migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
