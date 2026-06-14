"""Bootstrap SQLite DB when alembic fresh install fails (batch mode gaps)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from app.database import Base, engine
from app.services.blocks import ensure_block_catalog
from app.database import SessionLocal
from app.services.packs import ensure_system_packs


def main() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    try:
        command.upgrade(cfg, "head")
        print("[bootstrap] alembic upgrade head OK")
    except Exception as exc:
        print(f"[bootstrap] alembic failed ({exc}), using create_all + stamp")
        Base.metadata.create_all(bind=engine)
        command.stamp(cfg, "head")
        print("[bootstrap] create_all + stamp head OK")

    with SessionLocal() as db:
        ensure_system_packs(db)
        ensure_block_catalog(db)
        db.commit()
    print("[bootstrap] system packs + block catalog seeded")


if __name__ == "__main__":
    main()
