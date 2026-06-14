"""Truncate all data but keep schema; re-seed block_catalog and system packs."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlite3

from app.database import SessionLocal
from app.services.blocks import ensure_block_catalog
from app.services.packs import ensure_system_packs

DB_PATH = ROOT / "data" / "v3.db"


def truncate_all() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        tables = [
            row[0]
            for row in conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                  AND name != 'alembic_version'
                """
            )
        ]
        for table in tables:
            conn.execute(f'DELETE FROM "{table}"')
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
    print(f"[wipe] {len(tables)} tablas vaciadas")


def reseed_catalog() -> None:
    with SessionLocal() as db:
        ensure_system_packs(db)
        ensure_block_catalog(db)
        db.commit()
    print("[wipe] block_catalog + project_packs re-seeded")


if __name__ == "__main__":
    truncate_all()
    reseed_catalog()
