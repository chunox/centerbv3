"""
Migra proyectos Scrum legacy (epic/feature/task) al modelo v2 task-first.

Recomendado para demos: re-seed con seed_scrum_pack.py tras reset.

  .venv\\Scripts\\python.exe scripts/reset_and_seed_demo.py --seed-only --scrum-only
  .venv\\Scripts\\python.exe scripts/seed_scrum_pack.py

Este script documenta la migración manual; no ejecutar en producción sin backup.
"""
from __future__ import annotations

print(
    "Scrum v2 usa tasks con data.scrum_role (epic|story|dev) y sprint como parent_id.\n"
    "Para entornos demo, ejecute seed_scrum_pack.py en lugar de migración incremental."
)
