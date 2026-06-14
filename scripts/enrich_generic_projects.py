"""
Añade tipos, campos, vistas y registros demo a proyectos con pack genérico (evento, creativo, simple).

Uso (API no requerida):
  .venv\\Scripts\\python.exe scripts/enrich_generic_projects.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.database import SessionLocal
from app.models.entities import Project, ProjectRecord, User
from app.services.blocks import ensure_block_catalog
from app.services.generic_enrichment import (
    enrich_creativo_project,
    enrich_evento_project,
    enrich_simple_project,
)

TARGETS = {
    "Conferencia Producto 2026": "evento",
    "Campaña Verano Creativo": "creativo",
    "Consultoría ONG Demo": "simple",
}


def main() -> int:
    with SessionLocal() as db:
        ensure_block_catalog(db)
        db.commit()
        pm = db.scalar(select(User).where(User.email == "pm@center.demo"))
        if pm is None:
            print("No existe pm@center.demo — corré reset_and_seed_demo.py primero.")
            return 1

        today = date.today()
        for nombre, pack in TARGETS.items():
            project = db.scalar(
                select(Project).where(Project.nombre == nombre, Project.pack_slug == pack)
            )
            if project is None:
                print(f"[skip] Proyecto no encontrado: {nombre}")
                continue

            records = list(
                db.scalars(
                    select(ProjectRecord).where(ProjectRecord.project_id == project.id)
                )
            )
            if pack == "evento":
                root = next((r for r in records if r.record_type == "evento"), None)
                if not root:
                    print(f"[skip] Sin registro evento en {nombre}")
                    continue
                stats = enrich_evento_project(
                    db, project, evento_root_id=root.id, pm_id=pm.id, today=today
                )
            elif pack == "creativo":
                root = next((r for r in records if r.record_type == "campana"), None)
                if not root:
                    print(f"[skip] Sin campaña en {nombre}")
                    continue
                stats = enrich_creativo_project(
                    db, project, campana_root_id=root.id, pm_id=pm.id
                )
            else:
                fases = [r.id for r in records if r.record_type == "fase"]
                if not fases:
                    print(f"[skip] Sin fases en {nombre}")
                    continue
                stats = enrich_simple_project(
                    db, project, fase_ids=fases, pm_id=pm.id
                )

            print(f"[enrich] {nombre}: {stats}")

    print("Listo — recargá el frontend para ver las nuevas vistas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
