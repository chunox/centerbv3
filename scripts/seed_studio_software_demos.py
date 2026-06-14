"""
Crea 3 proyectos software con configuraciones muy distintas para probar Studio / Kanban.

Uso (API en :8000, usuarios demo existentes):
  .venv\\Scripts\\python.exe scripts/seed_studio_software_demos.py

Requiere pm@center.demo y el resto de usuarios demo (reset_and_seed_demo.py).
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

PROJECT_NAMES = (
    "Demo Studio · Cliente UAT",
    "Demo Studio · Kanban Grafo",
    "Demo Studio · Freestyle",
)

DEMO_USERS = [
    ("pm@center.demo", "Ana PM"),
    ("dev@center.demo", "Leo Dev"),
    ("dev2@center.demo", "Mía Dev2"),
    ("qa@center.demo", "Sofía QA"),
    ("cliente@center.demo", "Clara Cliente"),
]

# --- Definiciones custom ---

TASK_GRAPH_WORKFLOW: dict = {
    "states": [
        {"key": "backlog", "label": "Ideas", "category": "backlog", "badge": "info", "is_terminal": False},
        {"key": "todo", "label": "Seleccionado", "category": "todo", "badge": "info", "is_terminal": False},
        {"key": "in_progress", "label": "Desarrollo", "category": "active", "badge": "info", "is_terminal": False},
        {"key": "blocked", "label": "Bloqueado", "category": "active", "badge": "warning", "is_terminal": False},
        {"key": "review", "label": "Code review", "category": "active", "badge": "info", "is_terminal": False},
        {"key": "ready_for_test", "label": "QA", "category": "test", "badge": "info", "is_terminal": False},
        {"key": "completed", "label": "Hecho", "category": "done", "badge": "success", "is_terminal": True},
        {"key": "cancel", "label": "Descartado", "category": "terminal", "badge": "muted", "is_terminal": True},
    ],
    "initial_state": "backlog",
    "terminal_states": ["completed", "cancel"],
    "node_positions": {
        "backlog": {"x": 24, "y": 120},
        "todo": {"x": 228, "y": 48},
        "in_progress": {"x": 432, "y": 120},
        "blocked": {"x": 432, "y": 240},
        "review": {"x": 636, "y": 48},
        "ready_for_test": {"x": 840, "y": 120},
        "completed": {"x": 1044, "y": 48},
        "cancel": {"x": 1044, "y": 200},
    },
    "transitions": [
        {
            "id": "move",
            "label": "→ Seleccionado",
            "from": ["backlog"],
            "to": "todo",
            "required_capabilities": ["kanban.task.move"],
        },
        {
            "id": "move",
            "label": "→ Desarrollo",
            "from": ["todo"],
            "to": "in_progress",
            "required_capabilities": ["kanban.task.move"],
        },
        {
            "id": "move",
            "label": "→ Bloqueado",
            "from": ["in_progress"],
            "to": "blocked",
            "required_capabilities": ["kanban.task.move"],
            "allowed_role_slugs": ["pm_tecnico", "dev"],
        },
        {
            "id": "move",
            "label": "→ Desarrollo",
            "from": ["blocked"],
            "to": "in_progress",
            "required_capabilities": ["kanban.task.move"],
        },
        {
            "id": "move",
            "label": "→ Code review",
            "from": ["in_progress"],
            "to": "review",
            "required_capabilities": ["kanban.task.move"],
            "allowed_role_slugs": ["dev"],
        },
        {
            "id": "move",
            "label": "→ QA (shortcut PM)",
            "from": ["in_progress"],
            "to": "ready_for_test",
            "required_capabilities": ["kanban.task.move"],
            "allowed_role_slugs": ["pm_tecnico"],
        },
        {
            "id": "move",
            "label": "→ QA",
            "from": ["review"],
            "to": "ready_for_test",
            "required_capabilities": ["kanban.task.move"],
        },
        {
            "id": "move",
            "label": "→ Hecho",
            "from": ["ready_for_test"],
            "to": "completed",
            "required_capabilities": ["kanban.task.move"],
        },
        {
            "id": "cancel",
            "label": "Descartar",
            "from": ["backlog", "todo", "in_progress", "blocked", "review", "ready_for_test"],
            "to": "cancel",
            "required_capabilities": ["kanban.task.cancel"],
        },
    ],
}

TASK_MINIMAL_WORKFLOW: dict = {
    "states": [
        {"key": "backlog", "label": "Por hacer", "category": "backlog", "badge": "info", "is_terminal": False},
        {"key": "doing", "label": "En curso", "category": "active", "badge": "info", "is_terminal": False},
        {"key": "done", "label": "Listo", "category": "done", "badge": "success", "is_terminal": True},
        {"key": "cancel", "label": "Cancelado", "category": "terminal", "badge": "muted", "is_terminal": True},
    ],
    "initial_state": "backlog",
    "terminal_states": ["done", "cancel"],
    "node_positions": {
        "backlog": {"x": 80, "y": 80},
        "doing": {"x": 320, "y": 80},
        "done": {"x": 560, "y": 80},
        "cancel": {"x": 560, "y": 200},
    },
    "transitions": [
        {
            "id": "move",
            "label": "→ En curso",
            "from": ["backlog"],
            "to": "doing",
            "required_capabilities": ["kanban.task.move"],
        },
        {
            "id": "move",
            "label": "→ Listo",
            "from": ["doing"],
            "to": "done",
            "required_capabilities": ["kanban.task.move"],
        },
        {
            "id": "cancel",
            "label": "Cancelar",
            "from": ["backlog", "doing"],
            "to": "cancel",
            "required_capabilities": ["kanban.task.cancel"],
        },
    ],
}

FEATURE_MINIMAL_WORKFLOW: dict = {
    "states": [
        {"key": "pendiente", "label": "Pendiente", "category": "pending", "badge": "info", "is_terminal": False},
        {"key": "en_progreso", "label": "En progreso", "category": "active", "badge": "info", "is_terminal": False},
        {"key": "completado", "label": "Completado", "category": "terminal", "badge": "success", "is_terminal": True},
        {"key": "cancelado", "label": "Cancelado", "category": "terminal", "badge": "muted", "is_terminal": True},
    ],
    "initial_state": "pendiente",
    "terminal_states": ["completado", "cancelado"],
    "transitions": [
        {
            "id": "completar",
            "label": "Completar",
            "from": ["en_progreso"],
            "to": "completado",
            "required_capabilities": ["feature.transition.completar"],
        },
        {
            "id": "cancelar",
            "label": "Cancelar",
            "from": ["pendiente", "en_progreso"],
            "to": "cancelado",
            "required_capabilities": ["feature.transition.cancelar"],
            "side_effects": [{"type": "cancel_tasks_cascade"}],
        },
    ],
}

WORKBENCHES_GRAPH = [
    {
        "key": "overview",
        "label": "Resumen",
        "route": "overview",
        "icon": "layout-dashboard",
        "section": "pm",
        "required_capabilities": ["workbench.overview"],
        "orden": 10,
    },
    {
        "key": "kanban",
        "label": "Kanban",
        "route": "kanban",
        "icon": "columns-3",
        "section": "dev",
        "required_capabilities": ["workbench.kanban"],
        "orden": 20,
    },
    {
        "key": "my_tasks",
        "label": "Mis tareas",
        "route": "dev/my-tasks",
        "icon": "list-checks",
        "section": "dev",
        "required_capabilities": ["workbench.my_tasks"],
        "orden": 30,
    },
    {
        "key": "scope",
        "label": "Alcance",
        "route": "scope",
        "icon": "target",
        "section": "plan",
        "required_capabilities": ["workbench.scope"],
        "orden": 40,
    },
    {
        "key": "studio",
        "label": "Studio",
        "route": "studio",
        "icon": "layout-grid",
        "section": "admin",
        "required_capabilities": ["workbench.studio"],
        "orden": 50,
    },
    {
        "key": "settings",
        "label": "Configuración",
        "route": "settings",
        "icon": "settings",
        "section": "admin",
        "required_capabilities": ["workbench.settings"],
        "orden": 60,
    },
]

WORKBENCHES_FREESTYLE = [
    {
        "key": "studio",
        "label": "Studio",
        "route": "studio",
        "icon": "layout-grid",
        "section": "admin",
        "required_capabilities": ["workbench.studio"],
        "orden": 5,
    },
    {
        "key": "kanban",
        "label": "Kanban",
        "route": "kanban",
        "icon": "columns-3",
        "section": "dev",
        "required_capabilities": ["workbench.kanban"],
        "orden": 10,
    },
    {
        "key": "activity",
        "label": "Actividad",
        "route": "activity",
        "icon": "activity",
        "section": "track",
        "required_capabilities": ["workbench.activity"],
        "orden": 20,
    },
    {
        "key": "settings",
        "label": "Configuración",
        "route": "settings",
        "icon": "settings",
        "section": "admin",
        "required_capabilities": ["workbench.settings"],
        "orden": 99,
    },
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


def create_project(token: str, org_id: str, pm_id: str, **kwargs) -> dict:
    kwargs.setdefault("created_by", pm_id)
    kwargs.setdefault("organization_id", org_id)
    kwargs.setdefault("pack_slug", "software")
    return post(token, "/projects", kwargs)


def add_member(project_id: str, pm_id: str, user_id: str, rol: str, token: str) -> None:
    try:
        http(
            "POST",
            f"/projects/{project_id}/members",
            body={"actor_user_id": pm_id, "user_id": user_id, "rol": rol},
            token=token,
            expect_status=201,
        )
    except RuntimeError:
        pass


def put_workflow(token: str, project_id: str, pm_id: str, entity_type: str, definition: dict) -> dict:
    return put(
        token,
        f"/projects/{project_id}/workflows/{entity_type}",
        {"actor_user_id": pm_id, "definition": definition},
    )


def put_workbenches(token: str, project_id: str, pm_id: str, workbenches: list[dict]) -> list:
    return put(
        token,
        f"/projects/{project_id}/workbenches",
        {"actor_user_id": pm_id, "workbenches": workbenches},
    )


def create_milestone(token: str, project_id: str, pm_id: str, *, nombre: str, orden: int, start: str, end: str) -> dict:
    return post(
        token,
        f"/projects/{project_id}/milestones",
        {
            "nombre": nombre,
            "descripcion": "",
            "tipo": "entrega",
            "orden": orden,
            "fecha_inicio": start,
            "fecha_fin": end,
            "created_by": pm_id,
        },
    )


def create_feature(
    token: str,
    project_id: str,
    milestone_id: str,
    pm_id: str,
    *,
    nombre: str,
    estado: str,
    start: str,
    end: str,
) -> dict:
    return post(
        token,
        f"/projects/{project_id}/milestones/{milestone_id}/features",
        {
            "nombre": nombre,
            "descripcion": "",
            "tipo": "desarrollo",
            "prioridad": "media",
            "estado": estado,
            "fecha_inicio": start,
            "fecha_fin": end,
            "created_by": pm_id,
        },
    )


def project_has_milestones(token: str, project_id: str) -> bool:
    try:
        _, rows = http("GET", f"/projects/{project_id}/milestones", token=token)
        return bool(rows)
    except RuntimeError:
        return False


def create_task(
    token: str,
    project_id: str,
    milestone_id: str,
    feature_id: str,
    *,
    titulo: str,
    estado: str,
    created_by: str,
    asignado_ids: list[str] | None = None,
) -> dict:
    body: dict = {"titulo": titulo, "estado": estado, "created_by": created_by}
    if asignado_ids:
        body["asignado_ids"] = asignado_ids
    return post(
        token,
        f"/projects/{project_id}/milestones/{milestone_id}/features/{feature_id}/tasks",
        body,
    )


def ensure_project(
    token: str,
    org_id: str,
    pm_id: str,
    nombre: str,
    *,
    template_slug: str,
    descripcion: str,
    today: date,
) -> dict:
    existing = find_project_by_name(token, org_id, nombre)
    if existing:
        print(f"  [skip create] {nombre} ({existing['id']})")
        return existing
    project = create_project(
        token,
        org_id,
        pm_id,
        nombre=nombre,
        descripcion=descripcion,
        template_slug=template_slug,
        fecha_inicio=add_days(today, -14),
        fecha_fin=add_days(today, 90),
    )
    print(f"  [created] {nombre} ({project['id']})")
    return project


def seed_cliente_uat(
    token: str,
    org_id: str,
    today: date,
    users: dict[str, dict],
) -> dict:
    pm = users["pm@center.demo"]
    dev = users["dev@center.demo"]
    dev2 = users["dev2@center.demo"]
    qa = users["qa@center.demo"]
    cliente = users["cliente@center.demo"]
    nombre = PROJECT_NAMES[0]

    project = ensure_project(
        token,
        org_id,
        pm["id"],
        nombre,
        template_slug="t1_cliente_clasico",
        descripcion=(
            "Kanban estándar (5 columnas, move dinámico), menú completo, "
            "roles con cliente, features en UAT y bandejas PM/cliente."
        ),
        today=today,
    )
    pid = project["id"]

    for uid, rol in [
        (pm["id"], "pm"),
        (dev["id"], "dev"),
        (dev2["id"], "dev"),
        (qa["id"], "qa"),
        (cliente["id"], "cliente"),
    ]:
        add_member(pid, pm["id"], uid, rol, token)

    # Workflow y menú por defecto del template — sin PUT.

    if project_has_milestones(token, pid):
        print("  [skip data] ya tiene hitos")
        return {"nombre": nombre, "id": pid, "template": "t1_cliente_clasico", "config": "default kanban + menú completo"}

    ms = create_milestone(
        token, pid, pm["id"],
        nombre="Sprint UAT",
        orden=1,
        start=add_days(today, -10),
        end=add_days(today, 30),
    )
    feat_uat = create_feature(
        token, pid, ms["id"], pm["id"],
        nombre="Checkout express",
        estado="uat",
        start=add_days(today, -8),
        end=add_days(today, 20),
    )
    feat_client = create_feature(
        token, pid, ms["id"], pm["id"],
        nombre="Portal self-service",
        estado="esperando_validacion_cliente",
        start=add_days(today, -5),
        end=add_days(today, 25),
    )
    feat_prog = create_feature(
        token, pid, ms["id"], pm["id"],
        nombre="API facturación",
        estado="en_progreso",
        start=add_days(today, -3),
        end=add_days(today, 40),
    )

    standard_states = ["backlog", "to_do", "in_progress", "ready_for_test", "completed"]
    dev_ids = [dev["id"], dev2["id"]]
    for i, feat in enumerate([feat_uat, feat_client, feat_prog]):
        for j in range(8):
            create_task(
                token, pid, ms["id"], feat["id"],
                titulo=f"Tarea {feat['nombre'][:20]} #{j + 1}",
                estado=standard_states[(i + j) % len(standard_states)],
                created_by=dev_ids[j % 2],
                asignado_ids=[dev_ids[j % 2]],
            )

    return {"nombre": nombre, "id": pid, "template": "t1_cliente_clasico", "config": "default kanban + menú completo"}


def seed_kanban_grafo(
    token: str,
    org_id: str,
    today: date,
    users: dict[str, dict],
) -> dict:
    pm = users["pm@center.demo"]
    dev = users["dev@center.demo"]
    dev2 = users["dev2@center.demo"]
    qa = users["qa@center.demo"]
    nombre = PROJECT_NAMES[1]

    project = ensure_project(
        token,
        org_id,
        pm["id"],
        nombre,
        template_slug="t4_interno_pm_tecnico",
        descripcion=(
            "Kanban con grafo explícito (7 estados + bloqueo/review), "
            "menú recortado dev-first, roles pm_tecnico/dev/qa."
        ),
        today=today,
    )
    pid = project["id"]

    for uid, rol in [
        (pm["id"], "pm_tecnico"),
        (dev["id"], "dev"),
        (dev2["id"], "dev"),
        (qa["id"], "qa"),
    ]:
        add_member(pid, pm["id"], uid, rol, token)

    wf = put_workflow(token, pid, pm["id"], "task", TASK_GRAPH_WORKFLOW)
    put_workbenches(token, pid, pm["id"], WORKBENCHES_GRAPH)
    print(f"  task workflow v{wf.get('version')} · {len(wf.get('states', []))} estados")

    if project_has_milestones(token, pid):
        print("  [skip data] ya tiene hitos")
        return {
            "nombre": nombre,
            "id": pid,
            "template": "t4_interno_pm_tecnico",
            "config": "grafo 7 estados + menú recortado",
        }

    ms = create_milestone(
        token, pid, pm["id"],
        nombre="Release 2.4",
        orden=1,
        start=add_days(today, -7),
        end=add_days(today, 45),
    )
    feat = create_feature(
        token, pid, ms["id"], pm["id"],
        nombre="Refactor pagos",
        estado="en_progreso",
        start=add_days(today, -5),
        end=add_days(today, 30),
    )

    graph_states = ["backlog", "todo", "in_progress", "blocked", "review", "ready_for_test", "completed"]
    dev_ids = [dev["id"], dev2["id"]]
    for j in range(14):
        create_task(
            token, pid, ms["id"], feat["id"],
            titulo=f"Grafo demo #{j + 1}",
            estado=graph_states[j % len(graph_states)],
            created_by=dev_ids[j % 2],
            asignado_ids=[dev_ids[j % 2]],
        )

    return {
        "nombre": nombre,
        "id": pid,
        "template": "t4_interno_pm_tecnico",
        "config": "grafo 7 estados + menú recortado",
    }


def seed_freestyle(
    token: str,
    org_id: str,
    today: date,
    users: dict[str, dict],
) -> dict:
    pm = users["pm@center.demo"]
    dev = users["dev@center.demo"]
    cliente = users["cliente@center.demo"]
    nombre = PROJECT_NAMES[2]

    project = ensure_project(
        token,
        org_id,
        pm["id"],
        nombre,
        template_slug="t5_freestyle",
        descripcion=(
            "Kanban mínimo (3 columnas), feature workflow simplificado, "
            "menú ultra corto (Studio primero)."
        ),
        today=today,
    )
    pid = project["id"]

    for uid, rol in [
        (pm["id"], "pm"),
        (dev["id"], "dev"),
        (cliente["id"], "cliente"),
    ]:
        add_member(pid, pm["id"], uid, rol, token)

    put_workflow(token, pid, pm["id"], "task", TASK_MINIMAL_WORKFLOW)
    put_workflow(token, pid, pm["id"], "feature", FEATURE_MINIMAL_WORKFLOW)
    put_workbenches(token, pid, pm["id"], WORKBENCHES_FREESTYLE)

    if project_has_milestones(token, pid):
        print("  [skip data] ya tiene hitos")
        return {
            "nombre": nombre,
            "id": pid,
            "template": "t5_freestyle",
            "config": "3 cols + feature simple + menú mínimo",
        }

    ms = create_milestone(
        token, pid, pm["id"],
        nombre="Experimento",
        orden=1,
        start=add_days(today, -3),
        end=add_days(today, 60),
    )
    feat = create_feature(
        token, pid, ms["id"], pm["id"],
        nombre="Landing MVP",
        estado="en_progreso",
        start=add_days(today, -2),
        end=add_days(today, 30),
    )

    minimal_states = ["backlog", "doing", "done"]
    for j in range(6):
        create_task(
            token, pid, ms["id"], feat["id"],
            titulo=f"Minimal #{j + 1}",
            estado=minimal_states[j % 3],
            created_by=dev["id"],
            asignado_ids=[dev["id"]],
        )

    return {
        "nombre": nombre,
        "id": pid,
        "template": "t5_freestyle",
        "config": "3 cols + feature simple + menú mínimo",
    }


def main() -> None:
    wait_for_api()
    today = date.today()
    users = {email: ensure_user(email, nombre) for email, nombre in DEMO_USERS}
    pm = users["pm@center.demo"]

    auth = login(pm["email"])
    token = auth["access_token"]
    org_id = auth.get("organization_id")
    if not org_id:
        org = post(token, "/organizations", {"nombre": "Center Demo", "slug": "center-demo"})
        org_id = org["id"]
        auth = login(pm["email"])
        token = auth["access_token"]

    print("[seed] 3 proyectos Studio software…")
    results = [
        seed_cliente_uat(token, org_id, today, users),
        seed_kanban_grafo(token, org_id, today, users),
        seed_freestyle(token, org_id, today, users),
    ]

    print("\n=== Proyectos listos ===")
    for r in results:
        print(f"  · {r['nombre']}")
        print(f"    id={r['id']} · {r['template']} · {r['config']}")
    print("\nLogin: pm@center.demo / demo12345")
    print("Frontend: http://localhost:5173 (o el puerto de npm run dev)")


if __name__ == "__main__":
    main()
