"""
Proyecto demo de marketing con Kanban custom, roles custom y grafo con permisos por transición.

Uso (API en :8000, usuarios demo base):
  .venv\\Scripts\\python.exe scripts/seed_marketing_kanban_demo.py

Login sugerido:
  pm@center.demo / demo12345          → PM (configura Studio)
  mkt.lead@center.demo / demo12345    → Estratega (planifica y revisión marca)
  copy@center.demo / demo12345        → Copywriter (producción)
  design@center.demo / demo12345      → Diseño (producción)
  social@center.demo / demo12345      → Social media (producción)
  cliente@center.demo / demo12345     → Cliente (aprobación final)
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000/api/v1"
DEMO_PASSWORD = "demo12345"
PROJECT_NAME = "Campaña Marketing · Kanban Custom"

MARKETING_USERS = [
    ("pm@center.demo", "Ana PM"),
    ("mkt.lead@center.demo", "Lucía Estratega"),
    ("copy@center.demo", "Tomás Copy"),
    ("design@center.demo", "Valentina Diseño"),
    ("social@center.demo", "Nico Social"),
    ("cliente@center.demo", "Clara Cliente"),
]

# Kanban de campaña: brief → plan → producción → revisión → aprobación cliente → publicado
MARKETING_TASK_WORKFLOW: dict = {
    "states": [
        {"key": "backlog", "label": "Brief / Ideas", "category": "backlog", "badge": "muted", "is_terminal": False},
        {"key": "todo", "label": "Planificado", "category": "todo", "badge": "accent", "is_terminal": False},
        {"key": "in_progress", "label": "En producción", "category": "active", "badge": "info", "is_terminal": False},
        {"key": "review", "label": "Revisión interna", "category": "active", "badge": "warning", "is_terminal": False},
        {"key": "ready_for_test", "label": "Aprobación cliente", "category": "test", "badge": "success", "is_terminal": False},
        {"key": "completed", "label": "Publicado", "category": "done", "badge": "success", "is_terminal": True},
        {"key": "cancel", "label": "Descartado", "category": "terminal", "badge": "muted", "is_terminal": True},
    ],
    "initial_state": "backlog",
    "terminal_states": ["completed", "cancel"],
    "node_positions": {
        "backlog": {"x": 24, "y": 48},
        "todo": {"x": 228, "y": 48},
        "in_progress": {"x": 432, "y": 48},
        "review": {"x": 636, "y": 48},
        "ready_for_test": {"x": 840, "y": 48},
        "completed": {"x": 1044, "y": 48},
        "cancel": {"x": 840, "y": 200},
    },
    "transitions": [
        {
            "id": "move",
            "label": "→ Planificado",
            "from": ["backlog"],
            "to": "todo",
            "required_capabilities": ["kanban.task.move"],
            "allowed_role_slugs": ["pm", "marketing_lead"],
        },
        {
            "id": "move",
            "label": "→ En producción",
            "from": ["todo"],
            "to": "in_progress",
            "required_capabilities": ["kanban.task.move"],
            "allowed_role_slugs": ["copywriter", "designer", "social_media"],
        },
        {
            "id": "move",
            "label": "→ Revisión interna",
            "from": ["in_progress"],
            "to": "review",
            "required_capabilities": ["kanban.task.move"],
            "allowed_role_slugs": ["copywriter", "designer", "social_media"],
        },
        {
            "id": "move",
            "label": "→ Volver a producción",
            "from": ["review"],
            "to": "in_progress",
            "required_capabilities": ["kanban.task.move"],
            "allowed_role_slugs": ["marketing_lead", "pm"],
        },
        {
            "id": "move",
            "label": "→ Aprobación cliente",
            "from": ["review"],
            "to": "ready_for_test",
            "required_capabilities": ["kanban.task.move"],
            "allowed_role_slugs": ["marketing_lead", "pm"],
        },
        {
            "id": "move",
            "label": "→ Publicado",
            "from": ["ready_for_test"],
            "to": "completed",
            "required_capabilities": ["kanban.task.move"],
            "allowed_role_slugs": ["cliente", "pm"],
        },
        {
            "id": "move",
            "label": "→ Cambios solicitados",
            "from": ["ready_for_test"],
            "to": "in_progress",
            "required_capabilities": ["kanban.task.move"],
            "allowed_role_slugs": ["cliente", "pm"],
        },
        {
            "id": "cancel",
            "label": "Descartar pieza",
            "from": ["backlog", "todo", "in_progress", "review", "ready_for_test"],
            "to": "cancel",
            "required_capabilities": ["kanban.task.cancel"],
            "allowed_role_slugs": ["pm", "marketing_lead"],
        },
    ],
}

MARKETING_CUSTOM_ROLES: list[dict] = [
    {
        "slug": "marketing_lead",
        "nombre": "Estratega marketing",
        "capability_keys": [
            "workbench.overview",
            "workbench.scope",
            "workbench.kanban",
            "workbench.my_tasks",
            "workbench.studio",
            "workbench.settings",
            "kanban.view",
            "kanban.task.create",
            "kanban.task.edit",
            "kanban.task.move",
            "kanban.task.cancel",
            "kanban.task.assign",
            "scope.feature.create",
            "scope.feature.edit",
            "scope.milestone.create",
        ],
    },
    {
        "slug": "copywriter",
        "nombre": "Copywriter",
        "capability_keys": [
            "workbench.kanban",
            "workbench.my_tasks",
            "kanban.view",
            "kanban.task.edit",
            "kanban.task.move",
        ],
    },
    {
        "slug": "designer",
        "nombre": "Diseño",
        "capability_keys": [
            "workbench.kanban",
            "workbench.my_tasks",
            "kanban.view",
            "kanban.task.edit",
            "kanban.task.move",
        ],
    },
    {
        "slug": "social_media",
        "nombre": "Social media",
        "capability_keys": [
            "workbench.kanban",
            "workbench.my_tasks",
            "kanban.view",
            "kanban.task.edit",
            "kanban.task.move",
        ],
    },
]

MEMBER_ASSIGNMENTS = [
    ("pm@center.demo", "pm"),
    ("mkt.lead@center.demo", "marketing_lead"),
    ("copy@center.demo", "copywriter"),
    ("design@center.demo", "designer"),
    ("social@center.demo", "social_media"),
    ("cliente@center.demo", "cliente"),
]


def http(
    method: str,
    path: str,
    *,
    body: dict | None = None,
    token: str | None = None,
    expect_status: int | None = None,
) -> tuple[int, object]:
    url = f"{BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            status = res.status
            raw = res.read().decode()
            parsed = json.loads(raw) if raw else None
            if expect_status is not None and status != expect_status:
                raise RuntimeError(f"expected {expect_status}, got {status}: {raw[:400]}")
            return status, parsed
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        if expect_status is not None and e.code == expect_status:
            try:
                return e.code, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return e.code, raw
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {raw[:400]}") from e


def wait_for_api(max_wait: float = 60.0) -> None:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            req = urllib.request.Request("http://127.0.0.1:8000/health")
            with urllib.request.urlopen(req, timeout=5) as res:
                if res.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise RuntimeError("API no responde en :8000/health — iniciá uvicorn en :8000")


def add_days(base: date, days: int) -> str:
    return (base + timedelta(days=days)).isoformat()


def ensure_user(email: str, nombre: str) -> dict:
    _, users = http("GET", "/users")
    for u in users:
        if u["email"] == email:
            return u
    _, user = http(
        "POST",
        "/users",
        body={"email": email, "nombre": nombre, "password": DEMO_PASSWORD},
        expect_status=201,
    )
    return user


def login(email: str) -> dict:
    _, auth = http(
        "POST",
        "/auth/login",
        body={"email": email, "password": DEMO_PASSWORD},
        expect_status=200,
    )
    return auth


def post(token: str, path: str, body: dict, *, expect: int = 201) -> dict:
    _, data = http("POST", path, body=body, token=token, expect_status=expect)
    return data


def put(token: str, path: str, body: dict, *, expect: int = 200) -> dict:
    _, data = http("PUT", path, body=body, token=token, expect_status=expect)
    return data


def find_project_by_name(token: str, org_id: str, nombre: str) -> dict | None:
    _, projects = http(
        "GET",
        f"/projects?organization_id={org_id}&limit=200",
        token=token,
    )
    for p in projects:
        if p.get("nombre") == nombre:
            return p
    return None


def list_roles(token: str, project_id: str) -> list[dict]:
    _, roles = http("GET", f"/projects/{project_id}/roles", token=token)
    return roles if isinstance(roles, list) else []


def ensure_custom_roles(token: str, project_id: str, pm_id: str) -> dict[str, str]:
    """Returns slug -> role_id for custom roles."""
    slug_to_id: dict[str, str] = {}
    existing = {r["slug"]: r["id"] for r in list_roles(token, project_id)}

    for spec in MARKETING_CUSTOM_ROLES:
        slug = spec["slug"]
        if slug in existing:
            slug_to_id[slug] = existing[slug]
            print(f"  [skip role] {slug}")
            continue
        try:
            role = post(
                token,
                f"/projects/{project_id}/roles",
                {
                    "actor_user_id": pm_id,
                    "slug": slug,
                    "nombre": spec["nombre"],
                    "capability_keys": spec["capability_keys"],
                },
            )
            slug_to_id[slug] = role["id"]
            print(f"  [role] {spec['nombre']} ({slug})")
        except RuntimeError as err:
            if "409" in str(err) and slug in existing:
                slug_to_id[slug] = existing[slug]
                print(f"  [skip role] {slug}")
            else:
                raise

    for slug in ("pm", "cliente"):
        if slug in existing:
            slug_to_id[slug] = existing[slug]

    return slug_to_id


def add_member(
    token: str,
    project_id: str,
    pm_id: str,
    user_id: str,
    *,
    rol: str | None = None,
    role_id: str | None = None,
) -> None:
    body: dict = {"actor_user_id": pm_id, "user_id": user_id}
    if role_id:
        body["role_id"] = role_id
    elif rol:
        body["rol"] = rol
    try:
        http(
            "POST",
            f"/projects/{project_id}/members",
            body=body,
            token=token,
            expect_status=201,
        )
    except RuntimeError:
        pass


def project_has_milestones(token: str, project_id: str) -> bool:
    try:
        _, rows = http("GET", f"/projects/{project_id}/milestones", token=token)
        return bool(rows)
    except RuntimeError:
        return False


def seed_sample_data(
    token: str,
    project_id: str,
    pm_id: str,
    users: dict[str, dict],
    today: date,
) -> None:
    if not project_has_milestones(token, project_id):
        ms = post(
            token,
            f"/projects/{project_id}/milestones",
            {
                "nombre": "Lanzamiento Q3",
                "descripcion": "Campaña multicanal verano",
                "tipo": "entrega",
                "orden": 1,
                "fecha_inicio": add_days(today, -14),
                "fecha_fin": add_days(today, 60),
                "created_by": pm_id,
            },
        )
        feat = post(
            token,
            f"/projects/{project_id}/milestones/{ms['id']}/features",
            {
                "nombre": "Campaña redes · Verano",
                "descripcion": "Piezas para Instagram, LinkedIn y email",
                "tipo": "desarrollo",
                "prioridad": "alta",
                "estado": "en_progreso",
                "fecha_inicio": add_days(today, -10),
                "fecha_fin": add_days(today, 45),
                "created_by": pm_id,
            },
        )
        ms_id, feat_id = ms["id"], feat["id"]
    else:
        _, milestones = http("GET", f"/projects/{project_id}/milestones", token=token)
        ms_id = milestones[0]["id"]
        _, features = http(
            "GET",
            f"/projects/{project_id}/milestones/{ms_id}/features",
            token=token,
        )
        feat_id = features[0]["id"]
        _, existing_tasks = http(
            "GET",
            f"/projects/{project_id}/milestones/{ms_id}/features/{feat_id}/tasks",
            token=token,
        )
        if len(existing_tasks) >= 7:
            print("  [skip data] ya tiene hitos y tareas")
            return

    samples = [
        ("Brief post producto X", "backlog", "mkt.lead@center.demo"),
        ("Calendario editorial julio", "todo", "mkt.lead@center.demo"),
        ("Copy carrusel Instagram", "in_progress", "copy@center.demo"),
        ("Artes stories 9:16", "in_progress", "design@center.demo"),
        ("Hilo LinkedIn lanzamiento", "review", "copy@center.demo"),
        ("Pack ads Meta", "ready_for_test", "social@center.demo"),
        ("Newsletter julio #1", "completed", "copy@center.demo"),
    ]

    existing_titles: set[str] = set()
    try:
        _, existing_tasks = http(
            "GET",
            f"/projects/{project_id}/milestones/{ms_id}/features/{feat_id}/tasks",
            token=token,
        )
        existing_titles = {t.get("titulo") for t in existing_tasks if isinstance(t, dict)}
    except RuntimeError:
        pass

    created = 0
    for titulo, estado, owner_email in samples:
        if titulo in existing_titles:
            continue
        owner = users[owner_email]
        try:
            post(
                token,
                f"/projects/{project_id}/milestones/{ms_id}/features/{feat_id}/tasks",
                {
                    "titulo": titulo,
                    "estado": estado,
                    "created_by": users["mkt.lead@center.demo"]["id"],
                    "asignado_ids": [owner["id"]],
                },
            )
            created += 1
        except RuntimeError as err:
            if "403" in str(err):
                print(f"  [warn] no se pudo crear tarea '{titulo}' (permiso create)")
            else:
                raise

    print(f"  [data] +{created} tareas (total objetivo {len(samples)})")


def main() -> None:
    wait_for_api()
    today = date.today()
    users = {email: ensure_user(email, nombre) for email, nombre in MARKETING_USERS}
    pm = users["pm@center.demo"]

    auth = login(pm["email"])
    token = auth["access_token"]
    org_id = auth.get("organization_id")
    if not org_id:
        org = post(token, "/organizations", {"nombre": "Center Demo", "slug": "center-demo"})
        org_id = org["id"]
        auth = login(pm["email"])
        token = auth["access_token"]

    existing = find_project_by_name(token, org_id, PROJECT_NAME)
    if existing:
        project = existing
        print(f"[skip create] {PROJECT_NAME} ({project['id']})")
    else:
        project = post(
            token,
            "/projects",
            {
                "organization_id": org_id,
                "nombre": PROJECT_NAME,
                "descripcion": (
                    "Kanban de campaña con roles custom (estratega, copy, diseño, social, cliente) "
                    "y transiciones con permisos por conexión en el grafo."
                ),
                "pack_slug": "software",
                "template_slug": "t1_cliente_clasico",
                "profile_slug": "with_client",
                "fecha_inicio": add_days(today, -30),
                "fecha_fin": add_days(today, 120),
                "created_by": pm["id"],
            },
        )
        print(f"[created] {PROJECT_NAME} ({project['id']})")

    pid = project["id"]
    pm_id = pm["id"]

    print("[roles] custom marketing…")
    role_ids = ensure_custom_roles(token, pid, pm_id)

    print("[members]…")
    for email, role_slug in MEMBER_ASSIGNMENTS:
        user = users[email]
        if role_slug in role_ids and role_slug not in ("pm", "cliente"):
            add_member(token, pid, pm_id, user["id"], role_id=role_ids[role_slug])
        else:
            add_member(token, pid, pm_id, user["id"], rol=role_slug)
        print(f"  - {email} -> {role_slug}")

    print("[workflow] task kanban grafo…")
    wf = put(
        token,
        f"/projects/{pid}/workflows/task",
        {"actor_user_id": pm_id, "definition": MARKETING_TASK_WORKFLOW},
    )
    print(f"  task v{wf.get('version')} · {len(wf.get('states', []))} estados")

    print("[data] contenido demo…")
    seed_sample_data(token, pid, pm_id, users, today)

    print("\n=== Campaña Marketing lista ===")
    print(f"  Proyecto: {PROJECT_NAME}")
    print(f"  id={pid}")
    print("\n  Columnas Kanban:")
    for s in MARKETING_TASK_WORKFLOW["states"]:
        if not s.get("is_terminal") or s["key"] == "cancel":
            print(f"    - {s['label']} ({s['key']})")
    print("\n  Roles custom:")
    for r in MARKETING_CUSTOM_ROLES:
        print(f"    - {r['nombre']} ({r['slug']})")
    print("\n  Logins (password demo12345):")
    for email, _ in MARKETING_USERS:
        print(f"    - {email}")
    print("\n  Studio -> Flujos -> Tareas: ver grafo y roles por conexion")


if __name__ == "__main__":
    main()
