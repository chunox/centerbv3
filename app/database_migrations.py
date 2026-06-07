from pathlib import Path

from alembic import command
from alembic.config import Config


def _migration_config() -> Config:
    root = Path(__file__).resolve().parent.parent
    return Config(str(root / "alembic.ini"))


def run_migrations() -> None:
    """Aplica migraciones pendientes al arrancar la API."""
    cfg = _migration_config()
    command.upgrade(cfg, "head")
