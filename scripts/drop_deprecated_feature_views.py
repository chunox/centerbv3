"""Elimina vistas legacy de features / mis entregas de proyectos existentes."""
from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.workbenches import DEPRECATED_VIEW_ROUTES, DEPRECATED_WORKBENCH_KEYS
from app.models.entities import ProjectBlock, ProjectRoleCapability, ProjectView, ProjectWorkbenchDefinition

DEPRECATED_CAPS = frozenset({"workbench.features", "workbench.my_deliveries"})


def cleanup(*, dry_run: bool = True) -> dict[str, int]:
    stats = {"views": 0, "blocks": 0, "workbench_defs": 0, "capabilities": 0}
    with SessionLocal() as db:
        view_rows = list(
            db.scalars(
                select(ProjectView).where(
                    (ProjectView.key.in_(DEPRECATED_WORKBENCH_KEYS))
                    | (ProjectView.route.in_(DEPRECATED_VIEW_ROUTES))
                )
            )
        )
        stats["views"] = len(view_rows)
        if not dry_run:
            for row in view_rows:
                db.delete(row)

        block_rows = list(
            db.scalars(
                select(ProjectBlock).where(ProjectBlock.key.in_(DEPRECATED_WORKBENCH_KEYS))
            )
        )
        stats["blocks"] = len(block_rows)
        if not dry_run:
            for row in block_rows:
                db.delete(row)

        wb_rows = list(db.scalars(select(ProjectWorkbenchDefinition)))
        for row in wb_rows:
            stored = json.loads(row.definition or "[]")
            if not isinstance(stored, list):
                continue
            filtered = [
                wb
                for wb in stored
                if isinstance(wb, dict)
                and wb.get("key") not in DEPRECATED_WORKBENCH_KEYS
                and wb.get("route") not in DEPRECATED_VIEW_ROUTES
            ]
            if len(filtered) != len(stored):
                stats["workbench_defs"] += 1
                if not dry_run:
                    row.definition = json.dumps(filtered)

        cap_rows = list(
            db.scalars(
                select(ProjectRoleCapability).where(
                    ProjectRoleCapability.capability_key.in_(DEPRECATED_CAPS)
                )
            )
        )
        stats["capabilities"] = len(cap_rows)
        if not dry_run:
            for row in cap_rows:
                db.delete(row)

        if not dry_run:
            db.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persistir cambios")
    args = parser.parse_args()
    stats = cleanup(dry_run=not args.apply)
    mode = "aplicados" if args.apply else "pendientes (dry-run)"
    print(f"Limpieza {mode}:")
    for key, count in stats.items():
        print(f"  {key}: {count}")


if __name__ == "__main__":
    main()
