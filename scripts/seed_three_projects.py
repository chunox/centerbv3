"""
Borra datos y crea exactamente 3 proyectos demo:
  • 2 software (con cliente + interno) — plantilla software, datos poblados, roles
  • 1 marketing360 — briefing + piezas, roles copy/diseño/social/cliente

Uso (API en :8000):
  .venv\\Scripts\\python.exe scripts/seed_three_projects.py

Solo wipe (reiniciar uvicorn antes de seed):
  .venv\\Scripts\\python.exe scripts/seed_three_projects.py --reset-only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.reset_and_seed_demo import (  # noqa: E402
    DEMO_PASSWORD,
    DEMO_USERS,
    add_member,
    ensure_user,
    login,
    post,
    reset_database,
    seed_plataforma_interna,
    seed_portal_cliente,
    wait_for_api,
)
from scripts.seed_marketing360_demo import (  # noqa: E402
    M360_USERS,
    seed_marketing360_project,
)

SOFTWARE_PROJECTS = (
    "Portal Cliente Demo",
    "Plataforma Interna Center",
)
MARKETING_PROJECT = "Lanzamiento Q3 · Brand Awareness"


def configure_team_permissions() -> None:
    """Añade workbench Equipo + cap workbench.team a roles PM/owner."""
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "add_team_workbench.py")],
        cwd=ROOT,
        check=True,
    )


def seed_three_projects() -> None:
    wait_for_api()
    today = date.today()

    all_users = list(DEMO_USERS) + [u for u in M360_USERS if u not in DEMO_USERS]
    users = {email: ensure_user(email, nombre) for email, nombre in all_users}
    users.setdefault("cliente@center.demo", ensure_user("cliente@center.demo", "Clara Cliente"))

    pm = users["pm@center.demo"]
    auth = login(pm["email"])
    token = auth["access_token"]
    org_id = auth.get("organization_id")
    if not org_id:
        org = post(token, "/organizations", {"nombre": "Center Demo", "slug": "center-demo"})
        org_id = org["id"]
        auth = login(pm["email"])
        token = auth["access_token"]

    portal = seed_portal_cliente(token, org_id, today, users)
    interno = seed_plataforma_interna(token, org_id, today, users)
    marketing = seed_marketing360_project(token, org_id, pm["id"], today, users)

    # PM explícito en marketing (además del owner al crear)
    add_member(marketing["project_id"], pm["id"], pm["id"], "pm")

    configure_team_permissions()

    print("[seed] 3 proyectos OK")
    print(f"  • {portal['project']['nombre']} (software / con_cliente):")
    print(
        f"      {portal['milestones']} hitos, {portal['features']} features, "
        f"{portal['tasks']} tareas, {portal['queries']} consultas, {portal['reports']} reportes"
    )
    print(f"  • {interno['project']['nombre']} (software / interno):")
    print(
        f"      {interno['milestones']} hitos, {interno['features']} features, "
        f"{interno['tasks']} tareas, {interno['queries']} consultas"
    )
    print(f"  • {marketing['nombre']} (marketing360): {marketing['records']} registros")
    print("  Roles software: pm, dev, dev2, qa" + (", cliente (portal)" if True else ""))
    print("  Roles marketing: pm, copy, diseno, social, cliente")
    print("  Cuentas: " + ", ".join(e for e, _ in all_users))
    print(f"  Password: {DEMO_PASSWORD}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Wipe + 2 software + 1 marketing360")
    parser.add_argument("--reset-only", action="store_true")
    parser.add_argument("--seed-only", action="store_true")
    args = parser.parse_args()

    if not args.seed_only:
        reset_database()
        if args.reset_only:
            print("Reiniciá uvicorn y luego: python scripts/seed_three_projects.py --seed-only")
            return 0

    if not args.reset_only:
        try:
            seed_three_projects()
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            print("¿Está uvicorn en :8000? Tras --reset-only hay que reiniciar el servidor.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
