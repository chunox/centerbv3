"""Migra capacidades scope.*/kanban.task.*/query.*/report.* → record.* en roles de proyecto."""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.capabilities import resolve_capability_keys
from app.models.entities import ProjectRoleCapability


def canonical_record_key(key: str) -> str | None:
    for candidate in resolve_capability_keys([key]):
        if candidate.startswith("record.") and candidate != key:
            return candidate
    return None


def migrate(*, dry_run: bool = True) -> int:
    updated = 0
    with SessionLocal() as db:
        rows = list(db.scalars(select(ProjectRoleCapability)))
        for row in rows:
            replacement = canonical_record_key(row.capability_key)
            if replacement is None:
                continue
            exists = db.scalar(
                select(ProjectRoleCapability.id).where(
                    ProjectRoleCapability.role_id == row.role_id,
                    ProjectRoleCapability.capability_key == replacement,
                )
            )
            if exists:
                if not dry_run:
                    db.delete(row)
                updated += 1
                continue
            if not dry_run:
                row.capability_key = replacement
            updated += 1
        if not dry_run:
            db.commit()
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persistir cambios")
    args = parser.parse_args()
    count = migrate(dry_run=not args.apply)
    mode = "aplicados" if args.apply else "pendientes (dry-run)"
    print(f"Capacidades migradas: {count} ({mode})")


if __name__ == "__main__":
    main()
