"""Repara esquema desincronizado (tablas parciales) y lleva Alembic a head."""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v3.db"


def main() -> None:
    if not DB_PATH.exists():
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True)
        print("[repair] BD nueva, migraciones aplicadas.")
        return

    conn = sqlite3.connect(DB_PATH)
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    ver = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    current = ver[0] if ver else None
    print(f"[repair] alembic actual: {current}")

    # Migración a7 falló a medias: project_packs existe sin project_records.
    if "project_packs" in tables and "project_records" not in tables:
        print("[repair] Eliminando project_packs huérfana para re-aplicar migración…")
        conn.execute("DROP TABLE IF EXISTS project_packs")
        conn.commit()

    conn.close()

    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            check=True,
        )
        print("[repair] alembic upgrade head OK")
    except subprocess.CalledProcessError:
        # pack_slug u otras columnas ya existen: crear tablas faltantes vía metadata
        print("[repair] upgrade falló; creando tablas faltantes con SQLAlchemy…")
        sys.path.insert(0, str(ROOT))
        from app.database import Base, engine
        import app.models.entities  # noqa: F401

        Base.metadata.create_all(bind=engine, checkfirst=True)
        subprocess.run(
            [sys.executable, "-m", "alembic", "stamp", "head"],
            cwd=ROOT,
            check=True,
        )
        # Índices de b8 si faltan
        conn = sqlite3.connect(DB_PATH)
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )}
        if "idx_project_records_estado" not in indexes and "project_records" in {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_project_records_estado "
                "ON project_records (project_id, record_type, estado)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_project_records_fechas "
                "ON project_records (project_id, fecha_inicio, fecha_fin)"
            )
            conn.commit()
        conn.close()
        print("[repair] stamp head + índices OK")

    conn = sqlite3.connect(DB_PATH)
    ver = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    tables = sorted(
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    )
    print(f"[repair] alembic final: {ver[0] if ver else None}")
    for name in (
        "project_packs",
        "project_records",
        "project_record_types",
        "project_record_dependencies",
    ):
        print(f"  {name}: {'OK' if name in tables else 'MISSING'}")
    conn.close()


if __name__ == "__main__":
    main()
