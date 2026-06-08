"""
Reinicia data/v3.db y carga datos demo variados (paridad con seedDemo.ts v9).

Uso (con API en :8000):
  .venv\\Scripts\\python.exe scripts/reset_and_seed_demo.py

Solo borrar BD (reiniciar uvicorn antes de seed):
  .venv\\Scripts\\python.exe scripts/reset_and_seed_demo.py --reset-only

Solo seed (BD vacía, API arriba):
  .venv\\Scripts\\python.exe scripts/reset_and_seed_demo.py --seed-only
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "v3.db"
UPLOADS_DIR = DATA_DIR / "uploads"
BASE = "http://127.0.0.1:8000/api/v1"
DEMO_PASSWORD = "demo12345"
SEED_VERSION = "v9-rich"

DEMO_USERS = [
    ("pm@center.demo", "Ana PM"),
    ("dev@center.demo", "Leo Dev"),
    ("dev2@center.demo", "Mía Dev2"),
    ("qa@center.demo", "Sofía QA"),
    ("cliente@center.demo", "Clara Cliente"),
]

DEMO_PROJECTS = [
    "Portal Cliente Demo",
    "Sprint Interno",
    "App Móvil Retail",
    "Migración Legacy",
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
        with urllib.request.urlopen(req, timeout=60) as res:
            status = res.status
            raw = res.read().decode()
            parsed = json.loads(raw) if raw else None
            if expect_status is not None and status != expect_status:
                raise RuntimeError(f"expected {expect_status}, got {status}: {raw[:300]}")
            return status, parsed
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        if expect_status is not None and e.code == expect_status:
            return e.code, parsed
        raise RuntimeError(f"HTTP {e.code}: {raw[:400]}") from e


def wait_for_api(timeout_sec: int = 90) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            req = urllib.request.Request("http://127.0.0.1:8000/health")
            with urllib.request.urlopen(req, timeout=5) as res:
                if res.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("API no respondió en /health — iniciá uvicorn en :8000")


def truncate_database() -> None:
    import sqlite3

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
    print(f"[reset] Tablas vaciadas en {DB_PATH} (uvicorn puede seguir activo)")


def reset_database() -> None:
    if UPLOADS_DIR.exists():
        shutil.rmtree(UPLOADS_DIR, ignore_errors=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=ROOT,
                check=True,
            )
            print(f"[reset] BD nueva en {DB_PATH}")
            return
        except PermissionError:
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=ROOT,
                check=True,
            )
            truncate_database()
            return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        check=True,
    )
    print(f"[reset] BD nueva en {DB_PATH}")


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


def add_member(project_id: str, pm_id: str, user_id: str, rol: str) -> None:
    try:
        http(
            "POST",
            f"/projects/{project_id}/members",
            body={"actor_user_id": pm_id, "user_id": user_id, "rol": rol},
            expect_status=201,
        )
    except RuntimeError:
        pass


def seed_rich_demo() -> None:
    wait_for_api()
    today = date.today()
    users = {email: ensure_user(email, nombre) for email, nombre in DEMO_USERS}
    pm = users["pm@center.demo"]
    dev = users["dev@center.demo"]
    dev2 = users["dev2@center.demo"]
    qa = users["qa@center.demo"]
    cliente = users["cliente@center.demo"]

    auth = login(pm["email"])
    token = auth["access_token"]
    org_id = auth.get("organization_id")
    if not org_id:
        _, org = http(
            "POST",
            "/organizations",
            body={"nombre": "Center Demo", "slug": "center-demo"},
            token=token,
            expect_status=201,
        )
        org_id = org["id"]
        auth = login(pm["email"])
        token = auth["access_token"]

    def create_project(**kwargs) -> dict:
        _, project = http("POST", "/projects", body=kwargs, token=token, expect_status=201)
        return project

    # ── 1. Portal Cliente Demo ─────────────────────────────────────────────
    portal = create_project(
        organization_id=org_id,
        nombre="Portal Cliente Demo",
        descripcion="Cliente externo: inbox, reportes, consultas, hub y validación.",
        tipo="con_cliente",
        fecha_inicio=add_days(today, -30),
        fecha_fin=add_days(today, 90),
        created_by=pm["id"],
    )
    for uid, rol in [
        (pm["id"], "pm"),
        (dev["id"], "dev"),
        (dev2["id"], "dev"),
        (qa["id"], "qa"),
        (cliente["id"], "cliente"),
    ]:
        add_member(portal["id"], pm["id"], uid, rol)

    _, mvp = http(
        "POST",
        f"/projects/{portal['id']}/milestones",
        body={
            "nombre": "Entrega 1 — MVP",
            "descripcion": "Auth, dashboard y OAuth.",
            "tipo": "entrega",
            "orden": 1,
            "fecha_inicio": add_days(today, -30),
            "fecha_fin": add_days(today, 15),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    _, ent2 = http(
        "POST",
        f"/projects/{portal['id']}/milestones",
        body={
            "nombre": "Entrega 2 — Integraciones",
            "descripcion": "Exportaciones y conectores.",
            "tipo": "entrega",
            "orden": 2,
            "fecha_inicio": add_days(today, 16),
            "fecha_fin": add_days(today, 90),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    _, cancelled_ms = http(
        "POST",
        f"/projects/{portal['id']}/milestones",
        body={
            "nombre": "Spike descartado",
            "descripcion": "Hito cancelado para probar alcance avanzado.",
            "tipo": "entrega",
            "orden": 3,
            "fecha_inicio": add_days(today, -10),
            "fecha_fin": add_days(today, 5),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    http(
        "POST",
        f"/projects/{portal['id']}/milestones/{cancelled_ms['id']}/actions",
        body={"action": "cancelar", "actor_user_id": pm["id"], "actor_rol": "pm"},
        token=token,
        expect_status=200,
    )

    _, auth_feat = http(
        "POST",
        f"/projects/{portal['id']}/milestones/{mvp['id']}/features",
        body={
            "nombre": "Autenticación y roles",
            "descripcion": "Login, JWT y permisos por proyecto.",
            "tipo": "desarrollo",
            "prioridad": "alta",
            "estado": "en_progreso",
            "fecha_inicio": add_days(today, -25),
            "fecha_fin": add_days(today, 10),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    _, dashboard = http(
        "POST",
        f"/projects/{portal['id']}/milestones/{mvp['id']}/features",
        body={
            "nombre": "Dashboard PM",
            "descripcion": "Liberada — esperando validación cliente.",
            "tipo": "desarrollo",
            "prioridad": "media",
            "estado": "esperando_validacion_cliente",
            "fecha_inicio": add_days(today, -20),
            "fecha_fin": add_days(today, 5),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    _, oauth = http(
        "POST",
        f"/projects/{portal['id']}/milestones/{mvp['id']}/features",
        body={
            "nombre": "Login OAuth",
            "descripcion": "Completada — origen de reportes post-entrega.",
            "tipo": "desarrollo",
            "prioridad": "alta",
            "estado": "completado",
            "fecha_inicio": add_days(today, -28),
            "fecha_fin": add_days(today, -5),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    _, notifs = http(
        "POST",
        f"/projects/{portal['id']}/milestones/{mvp['id']}/features",
        body={
            "nombre": "Notificaciones in-app",
            "descripcion": "Campana y deep links.",
            "tipo": "desarrollo",
            "prioridad": "media",
            "estado": "esperando_liberacion_pm",
            "fecha_inicio": add_days(today, -15),
            "fecha_fin": add_days(today, 20),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    _, export_feat = http(
        "POST",
        f"/projects/{portal['id']}/milestones/{ent2['id']}/features",
        body={
            "nombre": "Export CSV actividad",
            "descripcion": "Feature en hito 2 para migrar entre hitos.",
            "tipo": "desarrollo",
            "prioridad": "baja",
            "estado": "pendiente",
            "fecha_inicio": add_days(today, 20),
            "fecha_fin": add_days(today, 60),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )

    # Tareas Kanban variadas
    for titulo, estado, asignado in [
        ("Spike permisos", "in_progress", dev["id"]),
        ("Selector de rol UI", "to_do", dev2["id"]),
        ("Tests E2E auth", "ready_for_test", dev["id"]),
        ("Doc OpenAPI", "backlog", None),
    ]:
        http(
            "POST",
            f"/projects/{portal['id']}/milestones/{mvp['id']}/features/{auth_feat['id']}/tasks",
            body={
                "titulo": titulo,
                "estado": estado,
                "asignado_a": asignado,
                "created_by": dev["id"],
            },
            token=token,
            expect_status=201,
        )

    # Consultas inbox
    _, q_active = http(
        "POST",
        f"/projects/{portal['id']}/milestones/{mvp['id']}/features/{auth_feat['id']}/queries",
        body={
            "titulo": "¿Usamos SSO corporativo?",
            "descripcion": "Cliente pregunta por IdP.",
            "created_by": dev["id"],
        },
        token=token,
        expect_status=201,
    )
    http(
        "POST",
        f"/projects/{portal['id']}/milestones/{mvp['id']}/features/{auth_feat['id']}/queries/{q_active['id']}/actions",
        body={"action": "activar", "actor_user_id": pm["id"], "actor_rol": "pm"},
        token=token,
        expect_status=200,
    )
    _, q_pending = http(
        "POST",
        f"/projects/{portal['id']}/milestones/{mvp['id']}/features/{auth_feat['id']}/queries",
        body={
            "titulo": "¿MFA obligatorio?",
            "descripcion": "Dev solicita envío al cliente.",
            "created_by": dev2["id"],
        },
        token=token,
        expect_status=201,
    )
    http(
        "POST",
        f"/projects/{portal['id']}/milestones/{mvp['id']}/features/{auth_feat['id']}/queries/{q_pending['id']}/actions",
        body={"action": "solicitar_envio", "actor_user_id": dev2["id"], "actor_rol": "dev"},
        token=token,
        expect_status=200,
    )

    # Reportes cliente
    http(
        "POST",
        f"/projects/{portal['id']}/milestones/{mvp['id']}/features/{oauth['id']}/reports",
        body={
            "tipo": "bug",
            "descripcion": "Sesión OAuth no persiste al recargar.",
            "reported_by": cliente["id"],
        },
        token=token,
        expect_status=201,
    )
    http(
        "POST",
        f"/projects/{portal['id']}/milestones/{mvp['id']}/features/{oauth['id']}/reports",
        body={
            "tipo": "mejora",
            "descripcion": "Recordar último proveedor OAuth usado.",
            "reported_by": cliente["id"],
        },
        token=token,
        expect_status=201,
    )

    # Hub documento + exposiciones
    _, doc = http(
        "POST",
        f"/projects/{portal['id']}/document",
        body={
            "titulo": "Especificación funcional MVP",
            "contenido": "Alcance: auth, dashboard, OAuth y notificaciones.",
            "visibilidad": "publico",
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    http(
        "POST",
        f"/projects/{portal['id']}/document-exposures",
        body={
            "ambito": "proyecto",
            "document_id": doc["id"],
            "titulo_visible": "Especificación MVP (cliente)",
            "expuesto_por": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    http(
        "POST",
        f"/projects/{portal['id']}/document-exposures",
        body={
            "ambito": "milestone",
            "milestone_id": mvp["id"],
            "document_id": doc["id"],
            "titulo_visible": "Alcance Entrega 1",
            "expuesto_por": pm["id"],
        },
        token=token,
        expect_status=201,
    )

    # Comentarios → timeline
    http(
        "POST",
        "/comments",
        body={
            "entidad_tipo": "feature",
            "entidad_id": auth_feat["id"],
            "user_id": dev["id"],
            "contenido": "Avance en spike de permisos — falta validar con PM.",
            "estado_momento": "en_progreso",
        },
        token=token,
        expect_status=201,
    )
    http(
        "POST",
        "/comments",
        body={
            "entidad_tipo": "feature",
            "entidad_id": dashboard["id"],
            "user_id": pm["id"],
            "contenido": "Liberado al cliente para validación UAT funcional.",
            "estado_momento": "esperando_validacion_cliente",
        },
        token=token,
        expect_status=201,
    )

    # ── 2. Sprint Interno ──────────────────────────────────────────────────
    interno = create_project(
        organization_id=org_id,
        nombre="Sprint Interno",
        descripcion="Solo equipo: UAT, consultas internas y Kanban denso.",
        tipo="interno",
        fecha_inicio=add_days(today, -14),
        fecha_fin=add_days(today, 75),
        created_by=pm["id"],
    )
    for uid, rol in [(pm["id"], "pm"), (dev["id"], "dev"), (dev2["id"], "dev"), (qa["id"], "qa")]:
        add_member(interno["id"], pm["id"], uid, rol)

    _, sprint1 = http(
        "POST",
        f"/projects/{interno['id']}/milestones",
        body={
            "nombre": "Sprint 1",
            "descripcion": "API + refactor tareas.",
            "tipo": "entrega",
            "orden": 1,
            "fecha_inicio": add_days(today, -14),
            "fecha_fin": add_days(today, 30),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    _, sprint2 = http(
        "POST",
        f"/projects/{interno['id']}/milestones",
        body={
            "nombre": "Sprint 2",
            "descripcion": "Performance y bundle BFF.",
            "tipo": "entrega",
            "orden": 2,
            "fecha_inicio": add_days(today, 31),
            "fecha_fin": add_days(today, 75),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )

    _, api_feat = http(
        "POST",
        f"/projects/{interno['id']}/milestones/{sprint1['id']}/features",
        body={
            "nombre": "API integración",
            "tipo": "desarrollo",
            "prioridad": "alta",
            "estado": "en_progreso",
            "fecha_inicio": add_days(today, -14),
            "fecha_fin": add_days(today, 20),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    _, refactor = http(
        "POST",
        f"/projects/{interno['id']}/milestones/{sprint1['id']}/features",
        body={
            "nombre": "Refactor módulo tareas",
            "tipo": "desarrollo",
            "prioridad": "media",
            "estado": "uat",
            "fecha_inicio": add_days(today, -10),
            "fecha_fin": add_days(today, 25),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    _, perf = http(
        "POST",
        f"/projects/{interno['id']}/milestones/{sprint2['id']}/features",
        body={
            "nombre": "Lazy-load vistas",
            "tipo": "desarrollo",
            "prioridad": "media",
            "estado": "pendiente",
            "fecha_inicio": add_days(today, 35),
            "fecha_fin": add_days(today, 70),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )

    for titulo, estado in [
        ("Cliente API centralizado", "in_progress"),
        ("Tipos en contexto React", "ready_for_test"),
        ("Paginación inbox", "to_do"),
    ]:
        http(
            "POST",
            f"/projects/{interno['id']}/milestones/{sprint1['id']}/features/{api_feat['id']}/tasks",
            body={"titulo": titulo, "estado": estado, "asignado_a": dev["id"], "created_by": dev["id"]},
            token=token,
            expect_status=201,
        )

    http(
        "POST",
        f"/projects/{interno['id']}/milestones/{sprint1['id']}/features/{refactor['id']}/tasks",
        body={
            "titulo": "Validar PATCH asignado_a",
            "estado": "ready_for_test",
            "asignado_a": dev["id"],
            "created_by": dev["id"],
        },
        token=token,
        expect_status=201,
    )
    http(
        "POST",
        "/comments",
        body={
            "entidad_tipo": "feature",
            "entidad_id": refactor["id"],
            "user_id": dev["id"],
            "contenido": "Handoff UAT: refactor listo para QA.",
            "estado_momento": "uat",
        },
        token=token,
        expect_status=201,
    )
    _, q_int = http(
        "POST",
        f"/projects/{interno['id']}/milestones/{sprint1['id']}/features/{api_feat['id']}/queries",
        body={
            "titulo": "URL API producción",
            "descripcion": "PM debe confirmar endpoint.",
            "created_by": dev2["id"],
        },
        token=token,
        expect_status=201,
    )
    http(
        "POST",
        f"/projects/{interno['id']}/milestones/{sprint1['id']}/features/{api_feat['id']}/queries/{q_int['id']}/actions",
        body={"action": "activar", "actor_user_id": pm["id"], "actor_rol": "pm"},
        token=token,
        expect_status=200,
    )

    http(
        "POST",
        f"/projects/{interno['id']}/document",
        body={
            "titulo": "Notas técnicas sprint 1",
            "contenido": "Solo equipo: contratos API internos.",
            "visibilidad": "interno",
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )

    # ── 3. App Móvil Retail ────────────────────────────────────────────────
    mobile = create_project(
        organization_id=org_id,
        nombre="App Móvil Retail",
        descripcion="Segundo proyecto con cliente: catálogo, carrito y pagos.",
        tipo="con_cliente",
        fecha_inicio=add_days(today, -7),
        fecha_fin=add_days(today, 120),
        created_by=pm["id"],
    )
    for uid, rol in [
        (pm["id"], "pm"),
        (dev2["id"], "dev"),
        (qa["id"], "qa"),
        (cliente["id"], "cliente"),
    ]:
        add_member(mobile["id"], pm["id"], uid, rol)

    _, ms_mobile = http(
        "POST",
        f"/projects/{mobile['id']}/milestones",
        body={
            "nombre": "Release 0.9 Beta",
            "tipo": "entrega",
            "orden": 1,
            "fecha_inicio": add_days(today, -7),
            "fecha_fin": add_days(today, 45),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    _, catalogo = http(
        "POST",
        f"/projects/{mobile['id']}/milestones/{ms_mobile['id']}/features",
        body={
            "nombre": "Catálogo productos",
            "tipo": "desarrollo",
            "prioridad": "alta",
            "estado": "uat",
            "fecha_inicio": add_days(today, -5),
            "fecha_fin": add_days(today, 30),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    _, pagos = http(
        "POST",
        f"/projects/{mobile['id']}/milestones/{ms_mobile['id']}/features",
        body={
            "nombre": "Checkout y pagos",
            "tipo": "desarrollo",
            "prioridad": "critica",
            "estado": "pendiente",
            "fecha_inicio": add_days(today, 10),
            "fecha_fin": add_days(today, 50),
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    http(
        "POST",
        f"/projects/{mobile['id']}/milestones/{ms_mobile['id']}/features/{catalogo['id']}/tasks",
        body={
            "titulo": "Listado con infinite scroll",
            "estado": "ready_for_test",
            "asignado_a": dev2["id"],
            "created_by": dev2["id"],
        },
        token=token,
        expect_status=201,
    )
    _, doc_mobile = http(
        "POST",
        f"/projects/{mobile['id']}/document",
        body={
            "titulo": "Guía de estilo móvil",
            "contenido": "Tipografía, colores y componentes.",
            "visibilidad": "publico",
            "created_by": pm["id"],
        },
        token=token,
        expect_status=201,
    )
    http(
        "POST",
        f"/projects/{mobile['id']}/document-exposures",
        body={
            "ambito": "feature",
            "milestone_id": ms_mobile["id"],
            "feature_id": catalogo["id"],
            "document_id": doc_mobile["id"],
            "titulo_visible": "Guía UI — Catálogo",
            "expuesto_por": pm["id"],
        },
        token=token,
        expect_status=201,
    )

    # ── 4. Migración Legacy (cerrado) ──────────────────────────────────────
    legacy = create_project(
        organization_id=org_id,
        nombre="Migración Legacy",
        descripcion="Proyecto cerrado para probar lectura-only en settings.",
        tipo="interno",
        fecha_inicio=add_days(today, -180),
        fecha_fin=add_days(today, -30),
        created_by=pm["id"],
    )
    add_member(legacy["id"], pm["id"], pm["id"], "pm")
    add_member(legacy["id"], pm["id"], dev["id"], "dev")
    http(
        "POST",
        f"/projects/{legacy['id']}/actions",
        body={"action": "cerrar", "actor_user_id": pm["id"], "actor_rol": "pm"},
        token=token,
        expect_status=200,
    )

    print(f"[seed] {SEED_VERSION} OK — {len(DEMO_USERS)} usuarios, {len(DEMO_PROJECTS)} proyectos")
    print("  Cuentas: " + ", ".join(e for e, _ in DEMO_USERS))
    print(f"  Password: {DEMO_PASSWORD}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset + seed demo Center v3")
    parser.add_argument("--reset-only", action="store_true")
    parser.add_argument("--seed-only", action="store_true")
    args = parser.parse_args()

    if not args.seed_only:
        reset_database()
        if args.reset_only:
            print("Reiniciá uvicorn y luego: python scripts/reset_and_seed_demo.py --seed-only")
            return 0

    if not args.reset_only:
        try:
            seed_rich_demo()
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            print("¿Está uvicorn en :8000? Tras --reset-only hay que reiniciar el servidor.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
