"""
Demo Scrum oficial: purge de proyectos + 2 proyectos ricos (t6 + t7).

  1. Logistics Hub       (t6_scrum_interno)
  2. E-commerce Relaunch   (t7_scrum_cliente)

Uso (API en :8000, usuarios demo):

  .venv\\Scripts\\python.exe scripts/reset_and_seed_demo.py --seed-only --scrum-only
  .venv\\Scripts\\python.exe scripts/seed_scrum_pack.py

No ejecutar migrate_scrum_epics.py tras este seed.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.seed_scrum_duo import seed_ecommerce
from scripts.seed_scrum_rich import (
    DEMO_PASSWORD,
    add_days,
    get_users,
    http,
    login,
    seed_logistics_hub,
)

BASE = "http://127.0.0.1:8000/api/v1"


def delete_project(token: str, project_id: str, actor_user_id: str) -> None:
    url = f"{BASE}/projects/{project_id}?actor_user_id={actor_user_id}"
    headers = {"Authorization": f"Bearer {token}"}
    req = urllib.request.Request(url, headers=headers, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            if res.status not in (200, 204):
                raise RuntimeError(f"DELETE {project_id}: {res.status}")
    except urllib.error.HTTPError as e:
        if e.code not in (200, 204, 404):
            raise RuntimeError(f"DELETE {project_id}: HTTP {e.code}") from e


def purge_all_projects(token: str, actor_user_id: str) -> int:
    _, projects = http("GET", "/projects", token=token)
    count = 0
    for p in projects or []:
        delete_project(token, p["id"], actor_user_id)
        count += 1
        print(f"  Eliminado: {p.get('nombre', p['id'])}")
    return count


def sync_sprint_velocity(token: str, project_id: str, sprint_id: str, actor_user_id: str) -> None:
    path = f"/projects/{project_id}/scrum/sprints/{sprint_id}/sync-velocity?actor_user_id={actor_user_id}"
    http("POST", path, token=token, expect_status=200)


def verify_pack(token: str, pm_id: str, logistics_id: str, ecommerce_id: str) -> None:
    def count_backlog(pid: str) -> int:
        rows = http(
            "GET",
            f"/projects/{pid}/records?record_type=task&in_product_backlog=true&actor_user_id={pm_id}",
            token=token,
        )[1]
        return len(rows or [])

    def count_epics(pid: str) -> int:
        rows = http(
            "GET",
            f"/projects/{pid}/records?record_type=task&actor_user_id={pm_id}",
            token=token,
        )[1]
        return len([r for r in (rows or []) if (r.get("data") or {}).get("scrum_role") == "epic"])

    def count_uat(pid: str) -> int:
        rows = http(
            "GET",
            f"/projects/{pid}/records?record_type=task&estado=uat&actor_user_id={pm_id}",
            token=token,
        )[1]
        return len([r for r in (rows or []) if (r.get("data") or {}).get("scrum_role") == "story"])

    lh_backlog = count_backlog(logistics_id)
    lh_epics = count_epics(logistics_id)
    lh_uat = count_uat(logistics_id)
    ec_backlog = count_backlog(ecommerce_id)
    ec_epics = count_epics(ecommerce_id)
    ec_uat = count_uat(ecommerce_id)

    print("\n[verify] Logistics Hub:")
    print(f"  epics={lh_epics} (esp. >=5), backlog={lh_backlog} (esp. >=10), uat={lh_uat} (esp. >=1)")
    print("[verify] E-commerce Relaunch:")
    print(f"  epics={ec_epics} (esp. >=4), backlog={ec_backlog} (esp. >=6), uat={ec_uat} (esp. >=1)")

    issues = []
    if lh_epics < 5:
        issues.append("Logistics: pocas épicas")
    if lh_backlog < 10:
        issues.append("Logistics: backlog insuficiente")
    if lh_uat < 1:
        issues.append("Logistics: sin historias UAT")
    if ec_epics < 4:
        issues.append("E-commerce: pocas épicas")
    if ec_backlog < 6:
        issues.append("E-commerce: backlog insuficiente")
    if ec_uat < 1:
        issues.append("E-commerce: sin historias UAT")
    if issues:
        print("[verify] ADVERTENCIAS:", "; ".join(issues))
    else:
        print("[verify] OK — datos dentro de expectativa")


def main() -> None:
    today = date.today()

    print("[seed-scrum-pack] Autenticando...")
    auth = login("pm@center.demo")
    token = auth["access_token"]
    users = get_users()
    pm_id = users["pm@center.demo"]["id"]

    required = [
        "pm@center.demo",
        "dev@center.demo",
        "dev2@center.demo",
        "qa@center.demo",
        "cliente@center.demo",
    ]
    missing = [e for e in required if e not in users]
    if missing:
        print(f"[ERROR] Usuarios faltantes: {missing}")
        print("Ejecuta: python scripts/reset_and_seed_demo.py --seed-only --scrum-only")
        sys.exit(1)

    auth_cliente = login("cliente@center.demo")
    token_cliente = auth_cliente["access_token"]

    _, orgs = http("GET", "/organizations", token=token)
    org_id = orgs[0]["id"]

    print("\n[seed-scrum-pack] Purge de proyectos existentes...")
    removed = purge_all_projects(token, pm_id)
    print(f"  {removed} proyecto(s) eliminado(s)")

    print("\n[1/2] Logistics Hub (t6_scrum_interno)...")
    lh_stats = seed_logistics_hub(token, users, org_id, today)
    logistics_id = lh_stats["project_id"]

    print("\n  Sync velocity Sprint 1...")
    sprints = http(
        "GET",
        f"/projects/{logistics_id}/scrum/sprints?actor_user_id={pm_id}",
        token=token,
    )[1]
    if sprints:
        s1 = next((s for s in sprints if s.get("orden") == 1), sprints[0])
        try:
            sync_sprint_velocity(token, logistics_id, s1["id"], pm_id)
            print(f"  horas_completadas sync en {s1['titulo'][:40]}")
        except RuntimeError as exc:
            print(f"  [warn] sync velocity: {exc}")

    print("\n[2/2] E-commerce Relaunch (t7_scrum_cliente)...")
    ecommerce_id = seed_ecommerce(token, token_cliente, users, org_id, today)

    print("\n[seed-scrum-pack] Listo.")
    print(f"  Logistics Hub:       http://localhost:5173/projects/{logistics_id}")
    print(f"  E-commerce Relaunch: http://localhost:5173/projects/{ecommerce_id}")
    verify_pack(token, pm_id, logistics_id, ecommerce_id)


if __name__ == "__main__":
    main()
