"""
Reinicia data/v3.db y carga 2 proyectos demo muy poblados (con_cliente + interno).

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
SEED_VERSION = "v10-dual-mega"

DEMO_USERS = [
    ("pm@center.demo", "Ana PM"),
    ("dev@center.demo", "Leo Dev"),
    ("dev2@center.demo", "Mía Dev2"),
    ("qa@center.demo", "Sofía QA"),
    ("cliente@center.demo", "Clara Cliente"),
]

DEMO_PROJECTS = [
    "Portal Cliente Demo",
    "Plataforma Interna Center",
]

TASK_STATES = ["backlog", "to_do", "in_progress", "ready_for_test", "completed"]
FEATURE_PRIORITIES = ["critica", "alta", "media", "baja"]


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


def post(token: str, path: str, body: dict, *, expect: int = 201) -> dict:
    _, data = http("POST", path, body=body, token=token, expect_status=expect)
    return data


def create_project(token: str, org_id: str, pm_id: str, **kwargs) -> dict:
    kwargs.setdefault("created_by", pm_id)
    kwargs.setdefault("organization_id", org_id)
    return post(token, "/projects", kwargs)


def create_milestone(
    token: str,
    project_id: str,
    pm_id: str,
    *,
    nombre: str,
    orden: int,
    fecha_inicio: str,
    fecha_fin: str,
    descripcion: str = "",
) -> dict:
    return post(
        token,
        f"/projects/{project_id}/milestones",
        {
            "nombre": nombre,
            "descripcion": descripcion,
            "tipo": "entrega",
            "orden": orden,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
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
    prioridad: str,
    fecha_inicio: str,
    fecha_fin: str,
    descripcion: str = "",
) -> dict:
    return post(
        token,
        f"/projects/{project_id}/milestones/{milestone_id}/features",
        {
            "nombre": nombre,
            "descripcion": descripcion,
            "tipo": "desarrollo",
            "prioridad": prioridad,
            "estado": estado,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "created_by": pm_id,
        },
    )


def create_task(
    token: str,
    project_id: str,
    milestone_id: str,
    feature_id: str,
    *,
    titulo: str,
    estado: str,
    created_by: str,
    asignado_a: str | None = None,
    descripcion: str = "",
) -> dict:
    body: dict = {
        "titulo": titulo,
        "estado": estado,
        "created_by": created_by,
    }
    if asignado_a:
        body["asignado_a"] = asignado_a
    if descripcion:
        body["descripcion"] = descripcion
    return post(
        token,
        f"/projects/{project_id}/milestones/{milestone_id}/features/{feature_id}/tasks",
        body,
    )


def create_comment(
    token: str,
    *,
    entidad_tipo: str,
    entidad_id: str,
    user_id: str,
    contenido: str,
    estado_momento: str,
) -> None:
    post(
        token,
        "/comments",
        {
            "entidad_tipo": entidad_tipo,
            "entidad_id": entidad_id,
            "user_id": user_id,
            "contenido": contenido,
            "estado_momento": estado_momento,
        },
    )


def seed_tasks_for_feature(
    token: str,
    project_id: str,
    milestone_id: str,
    feature_id: str,
    feature_nombre: str,
    dev_ids: list[str],
    *,
    count: int = 10,
) -> int:
    prefixes = [
        "Implementar",
        "Refinar",
        "Tests",
        "Revisar",
        "Documentar",
        "Spike",
        "Fix",
        "Integrar",
        "Validar",
        "Optimizar",
        "Migrar",
        "Diseñar",
    ]
    created = 0
    for i in range(count):
        dev = dev_ids[i % len(dev_ids)]
        titulo = f"{prefixes[i % len(prefixes)]} {feature_nombre} #{i + 1}"
        create_task(
            token,
            project_id,
            milestone_id,
            feature_id,
            titulo=titulo,
            estado=TASK_STATES[i % len(TASK_STATES)],
            created_by=dev,
            asignado_a=dev if i % 4 != 3 else None,
            descripcion=f"Tarea demo {i + 1} para {feature_nombre}.",
        )
        created += 1
    return created


def seed_portal_cliente(
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
    dev_ids = [dev["id"], dev2["id"]]

    portal = create_project(
        token,
        org_id,
        pm["id"],
        nombre="Portal Cliente Demo",
        descripcion=(
            "Proyecto con cliente externo: inbox denso, reportes, consultas, "
            "hub, validación UAT y Kanban con muchas tareas."
        ),
        tipo="con_cliente",
        fecha_inicio=add_days(today, -45),
        fecha_fin=add_days(today, 120),
    )
    for uid, rol in [
        (pm["id"], "pm"),
        (dev["id"], "dev"),
        (dev2["id"], "dev"),
        (qa["id"], "qa"),
        (cliente["id"], "cliente"),
    ]:
        add_member(portal["id"], pm["id"], uid, rol)

    milestones_spec = [
        ("Entrega 1 — MVP", 1, -45, 20, "Auth, dashboard, OAuth y notificaciones."),
        ("Entrega 2 — Integraciones", 2, 21, 60, "Exportaciones, webhooks y conectores."),
        ("Entrega 3 — Analytics", 3, 61, 100, "Dashboards, métricas y alertas."),
        ("Entrega 4 — Mobile web", 4, 101, 120, "PWA, push y offline básico."),
        ("Spike descartado", 5, -10, 5, "Hito cancelado para probar alcance."),
    ]
    milestones: list[dict] = []
    for nombre, orden, start, end, desc in milestones_spec:
        ms = create_milestone(
            token,
            portal["id"],
            pm["id"],
            nombre=nombre,
            orden=orden,
            fecha_inicio=add_days(today, start),
            fecha_fin=add_days(today, end),
            descripcion=desc,
        )
        milestones.append(ms)

    http(
        "POST",
        f"/projects/{portal['id']}/milestones/{milestones[4]['id']}/actions",
        body={"action": "cancelar", "actor_user_id": pm["id"], "actor_rol": "pm"},
        token=token,
        expect_status=200,
    )

    features_spec: list[tuple[int, str, str, str, int, int]] = [
        # (milestone_idx, nombre, estado, prioridad, start_offset, end_offset)
        (0, "Autenticación y roles", "en_progreso", "alta", -40, 15),
        (0, "Dashboard PM", "esperando_validacion_cliente", "media", -35, 10),
        (0, "Login OAuth", "completado", "alta", -42, -5),
        (0, "Notificaciones in-app", "esperando_liberacion_pm", "media", -30, 18),
        (0, "Onboarding wizard", "uat", "media", -25, 12),
        (0, "Permisos granulares", "en_progreso", "critica", -38, 8),
        (1, "Export CSV actividad", "pendiente", "baja", 25, 55),
        (1, "Webhooks salientes", "en_progreso", "alta", 22, 50),
        (1, "Conector Salesforce", "pendiente", "media", 30, 58),
        (1, "API pública v1", "uat", "alta", 24, 45),
        (1, "Sync nocturno ERP", "en_progreso", "media", 26, 52),
        (2, "Dashboard métricas uso", "pendiente", "media", 65, 95),
        (2, "Alertas por email", "pendiente", "baja", 70, 98),
        (2, "Embudo conversión", "pendiente", "alta", 68, 90),
        (3, "PWA shell", "pendiente", "media", 105, 118),
        (3, "Push notifications", "pendiente", "alta", 108, 119),
        (4, "POC GraphQL", "cancelado", "baja", -8, 2),
    ]

    features: list[dict] = []
    task_total = 0
    active_feature_indices = [0, 1, 3, 4, 5, 7, 8, 9, 10]

    for ms_idx, nombre, estado, prioridad, start, end in features_spec:
        feat = create_feature(
            token,
            portal["id"],
            milestones[ms_idx]["id"],
            pm["id"],
            nombre=nombre,
            estado=estado,
            prioridad=prioridad,
            fecha_inicio=add_days(today, start),
            fecha_fin=add_days(today, end),
            descripcion=f"Feature demo «{nombre}» en hito {ms_idx + 1}.",
        )
        features.append(feat)
        idx = len(features) - 1
        if estado not in ("completado", "cancelado") and idx in active_feature_indices:
            n_tasks = 12 if prioridad in ("critica", "alta") else 8
            task_total += seed_tasks_for_feature(
                token,
                portal["id"],
                milestones[ms_idx]["id"],
                feat["id"],
                nombre,
                dev_ids,
                count=n_tasks,
            )

    auth_feat = features[0]
    oauth = features[2]
    webhooks = features[8]

    queries_spec = [
        (0, "¿Usamos SSO corporativo?", "Cliente pregunta por IdP.", dev["id"], "activar"),
        (0, "¿MFA obligatorio?", "Dev solicita envío al cliente.", dev2["id"], "solicitar_envio"),
        (0, "Política de sesiones", "Duración refresh token.", dev["id"], "activar"),
        (5, "Matriz permisos v2", "PM debe validar roles.", dev2["id"], "activar"),
        (7, "Rate limit webhooks", "¿Cuántos eventos/min?", dev["id"], "solicitar_envio"),
        (8, "Sandbox Salesforce", "Credenciales de prueba.", dev2["id"], "activar"),
        (9, "Versionado API pública", "Semver o fecha.", dev["id"], "activar"),
        (10, "Ventana sync ERP", "Horario batch nocturno.", dev2["id"], "solicitar_envio"),
    ]
    for feat_idx, titulo, desc, author, action in queries_spec:
        feat = features[feat_idx]
        ms_id = milestones[features_spec[feat_idx][0]]["id"]
        q = post(
            token,
            f"/projects/{portal['id']}/milestones/{ms_id}/features/{feat['id']}/queries",
            {"titulo": titulo, "descripcion": desc, "created_by": author},
        )
        actor = dev["id"] if action == "solicitar_envio" else pm["id"]
        rol = "dev" if action == "solicitar_envio" else "pm"
        post(
            token,
            f"/projects/{portal['id']}/milestones/{ms_id}/features/{feat['id']}/queries/{q['id']}/actions",
            {"action": action, "actor_user_id": actor, "actor_rol": rol},
            expect=200,
        )

    reports_spec = [
        (2, "bug", "Sesión OAuth no persiste al recargar."),
        (2, "mejora", "Recordar último proveedor OAuth usado."),
        (2, "bug", "Redirect loop en logout Google."),
        (2, "mejora", "Botón «Continuar con Microsoft» más visible."),
        (2, "bug", "Error 500 al vincular cuenta existente."),
        (2, "mejora", "Tooltip explicando scopes OAuth."),
    ]
    for feat_idx, tipo, desc in reports_spec:
        feat = features[feat_idx]
        ms_id = milestones[features_spec[feat_idx][0]]["id"]
        post(
            token,
            f"/projects/{portal['id']}/milestones/{ms_id}/features/{feat['id']}/reports",
            {"tipo": tipo, "descripcion": desc, "reported_by": cliente["id"]},
        )

    doc = post(
        token,
        f"/projects/{portal['id']}/document",
        {
            "titulo": "Especificación funcional Portal Cliente",
            "contenido": (
                "Alcance MVP: auth, dashboard, OAuth, notificaciones.\n\n"
                "Integraciones: webhooks, Salesforce, API pública.\n\n"
                "Analytics y mobile web en entregas posteriores."
            ),
            "visibilidad": "publico",
            "created_by": pm["id"],
        },
    )
    post(
        token,
        f"/projects/{portal['id']}/document-exposures",
        {
            "ambito": "proyecto",
            "document_id": doc["id"],
            "titulo_visible": "Especificación completa (cliente)",
            "expuesto_por": pm["id"],
        },
    )
    post(
        token,
        f"/projects/{portal['id']}/document-exposures",
        {
            "ambito": "milestone",
            "milestone_id": milestones[0]["id"],
            "document_id": doc["id"],
            "titulo_visible": "Alcance Entrega 1 — MVP",
            "expuesto_por": pm["id"],
        },
    )
    post(
        token,
        f"/projects/{portal['id']}/document-exposures",
        {
            "ambito": "feature",
            "milestone_id": milestones[1]["id"],
            "feature_id": webhooks["id"],
            "document_id": doc["id"],
            "titulo_visible": "Webhooks — anexo técnico",
            "expuesto_por": pm["id"],
        },
    )

    hub_updates = [
        ("OAuth Google listo en staging.", dev["id"], "publico", None),
        ("Dashboard PM liberado al cliente.", pm["id"], "publico", None),
        ("Inicio sprint integraciones.", pm["id"], "publico", None),
        ("Webhooks: primer conector en QA.", dev2["id"], "publico", None),
        ("Retraso menor en Salesforce sandbox.", pm["id"], "publico", None),
        ("Cliente confirmó alcance analytics.", pm["id"], "publico", None),
        ("Deploy hotfix auth middleware.", dev["id"], "interno", None),
        ("Revisión seguridad pendiente.", dev2["id"], "interno", None),
    ]
    hub_notes = [
        ("Decisiones MVP", "Notificaciones push fuera del MVP.", pm["id"], "publico"),
        ("Acuerdo SLA", "Respuesta consultas < 48h hábiles.", pm["id"], "publico"),
        ("Deuda técnica", "Refactor permisos post-entrega 2.", dev["id"], "interno"),
    ]
    for contenido, author, vis, _ in hub_updates:
        post(
            token,
            f"/projects/{portal['id']}/hub-entries",
            {
                "author_id": author,
                "tipo": "update",
                "contenido": contenido,
                "visibilidad": vis,
            },
        )
    for titulo, contenido, author, vis in hub_notes:
        post(
            token,
            f"/projects/{portal['id']}/hub-entries",
            {
                "author_id": author,
                "tipo": "note",
                "titulo": titulo,
                "contenido": contenido,
                "visibilidad": vis,
            },
        )

    for i, feat in enumerate(features[:12]):
        create_comment(
            token,
            entidad_tipo="feature",
            entidad_id=feat["id"],
            user_id=dev_ids[i % 2],
            contenido=f"Comentario demo #{i + 1} en {feat['nombre'][:40]}.",
            estado_momento=features_spec[i][2],
        )

    return {
        "project": portal,
        "milestones": len(milestones),
        "features": len(features),
        "tasks": task_total,
        "queries": len(queries_spec),
        "reports": len(reports_spec),
    }


def seed_plataforma_interna(
    token: str,
    org_id: str,
    today: date,
    users: dict[str, dict],
) -> dict:
    pm = users["pm@center.demo"]
    dev = users["dev@center.demo"]
    dev2 = users["dev2@center.demo"]
    qa = users["qa@center.demo"]
    dev_ids = [dev["id"], dev2["id"]]

    interno = create_project(
        token,
        org_id,
        pm["id"],
        nombre="Plataforma Interna Center",
        descripcion=(
            "Proyecto interno: múltiples sprints, UAT denso, consultas PM, "
            "hub interno y Kanban con decenas de tareas."
        ),
        tipo="interno",
        fecha_inicio=add_days(today, -30),
        fecha_fin=add_days(today, 90),
    )
    for uid, rol in [
        (pm["id"], "pm"),
        (dev["id"], "dev"),
        (dev2["id"], "dev"),
        (qa["id"], "qa"),
    ]:
        add_member(interno["id"], pm["id"], uid, rol)

    milestones_spec = [
        ("Sprint 1 — Fundaciones", 1, -30, 0, "API, auth interna y layout."),
        ("Sprint 2 — Colaboración", 2, 1, 30, "Inbox, comentarios y hub."),
        ("Sprint 3 — PM tools", 3, 31, 55, "Portfolio, timeline y alcance."),
        ("Sprint 4 — Dev workspace", 4, 56, 75, "Kanban, entregas y queries."),
        ("Sprint 5 — Hardening", 5, 76, 90, "Performance, tests E2E y docs."),
    ]
    milestones: list[dict] = []
    for nombre, orden, start, end, desc in milestones_spec:
        ms = create_milestone(
            token,
            interno["id"],
            pm["id"],
            nombre=nombre,
            orden=orden,
            fecha_inicio=add_days(today, start),
            fecha_fin=add_days(today, end),
            descripcion=desc,
        )
        milestones.append(ms)

    features_spec: list[tuple[int, str, str, str, int, int]] = [
        (0, "API integración central", "en_progreso", "alta", -28, 5),
        (0, "Auth tokens internos", "en_progreso", "critica", -25, 8),
        (0, "Layout shell v3", "uat", "media", -22, 10),
        (0, "Migración SQLite → PG", "pendiente", "alta", -20, 15),
        (1, "Inbox unificado PM", "en_progreso", "alta", -5, 25),
        (1, "Hilos de comentarios", "uat", "media", -3, 28),
        (1, "Hub documentación", "en_progreso", "media", 0, 30),
        (1, "Notificaciones in-app", "pendiente", "baja", 5, 32),
        (2, "Portfolio salud", "en_progreso", "alta", 32, 50),
        (2, "Timeline Gantt", "uat", "media", 35, 52),
        (2, "Alcance editorial", "en_progreso", "media", 38, 54),
        (2, "Features globales", "pendiente", "baja", 40, 55),
        (3, "Kanban swimlanes", "en_progreso", "alta", 58, 72),
        (3, "Mis entregas dev", "uat", "media", 60, 74),
        (3, "Consultas bloqueantes", "en_progreso", "critica", 62, 70),
        (3, "Task detail modal", "pendiente", "media", 65, 73),
        (4, "Bundle splitting", "pendiente", "media", 78, 88),
        (4, "Tests E2E Playwright", "pendiente", "alta", 80, 89),
        (4, "Observabilidad logs", "pendiente", "baja", 82, 90),
    ]

    features: list[dict] = []
    task_total = 0
    for ms_idx, nombre, estado, prioridad, start, end in features_spec:
        feat = create_feature(
            token,
            interno["id"],
            milestones[ms_idx]["id"],
            pm["id"],
            nombre=nombre,
            estado=estado,
            prioridad=prioridad,
            fecha_inicio=add_days(today, start),
            fecha_fin=add_days(today, end),
            descripcion=f"Feature interna «{nombre}».",
        )
        features.append(feat)
        if estado not in ("cancelado",):
            n_tasks = 14 if prioridad in ("critica", "alta") else 9
            task_total += seed_tasks_for_feature(
                token,
                interno["id"],
                milestones[ms_idx]["id"],
                feat["id"],
                nombre,
                dev_ids,
                count=n_tasks,
            )

    queries_spec = [
        (0, "URL API producción", "PM debe confirmar endpoint.", dev2["id"]),
        (1, "Política refresh tokens", "Duración y rotación.", dev["id"]),
        (4, "Prioridad inbox vs email", "¿Unificar bandejas?", dev2["id"]),
        (6, "Visibilidad docs internos", "Reglas hub vs document.", dev["id"]),
        (8, "Métricas portfolio", "Definición 'at risk'.", dev2["id"]),
        (12, "Drag entre columnas", "Reglas QA en Kanban.", dev["id"]),
        (14, "Estados consulta interna", "Flujo cierre PM.", dev2["id"]),
    ]
    for feat_idx, titulo, desc, author in queries_spec:
        feat = features[feat_idx]
        ms_id = milestones[features_spec[feat_idx][0]]["id"]
        q = post(
            token,
            f"/projects/{interno['id']}/milestones/{ms_id}/features/{feat['id']}/queries",
            {"titulo": titulo, "descripcion": desc, "created_by": author},
        )
        post(
            token,
            f"/projects/{interno['id']}/milestones/{ms_id}/features/{feat['id']}/queries/{q['id']}/actions",
            {"action": "activar", "actor_user_id": pm["id"], "actor_rol": "pm"},
            expect=200,
        )

    post(
        token,
        f"/projects/{interno['id']}/document",
        {
            "titulo": "Wiki técnica Plataforma Interna",
            "contenido": (
                "Contratos API, ADRs, runbooks y checklists de release.\n\n"
                "Solo visible para el equipo (visibilidad interno)."
            ),
            "visibilidad": "interno",
            "created_by": pm["id"],
        },
    )

    for contenido, author in [
        ("API central: primer endpoint estable.", dev["id"]),
        ("Layout v3 en rama main.", dev2["id"]),
        ("Inbox PM: filtros por tab.", dev["id"]),
        ("Timeline: hitos solapados OK.", pm["id"]),
        ("Kanban: scroll fix en dev.", dev2["id"]),
        ("QA: suite UAT ampliada.", dev["id"]),
        ("Refactor acceso documentos.", dev["id"]),
        ("Seed demo v10 desplegado.", pm["id"]),
    ]:
        post(
            token,
            f"/projects/{interno['id']}/hub-entries",
            {
                "author_id": author,
                "tipo": "update",
                "contenido": contenido,
                "visibilidad": "interno",
            },
        )

    for titulo, contenido, author in [
        ("Convención commits", "Conventional commits + scope.", pm["id"]),
        ("Deuda Q3", "Migración PG y cache Redis.", dev["id"]),
        ("QA focus", "UAT gates por feature.", pm["id"]),
    ]:
        post(
            token,
            f"/projects/{interno['id']}/hub-entries",
            {
                "author_id": author,
                "tipo": "note",
                "titulo": titulo,
                "contenido": contenido,
                "visibilidad": "interno",
            },
        )

    for i, feat in enumerate(features):
        create_comment(
            token,
            entidad_tipo="feature",
            entidad_id=feat["id"],
            user_id=dev_ids[i % 2],
            contenido=f"Seguimiento interno #{i + 1}: {feat['nombre'][:35]}.",
            estado_momento=features_spec[i][2],
        )

    return {
        "project": interno,
        "milestones": len(milestones),
        "features": len(features),
        "tasks": task_total,
        "queries": len(queries_spec),
    }


def seed_rich_demo() -> None:
    wait_for_api()
    today = date.today()
    users = {email: ensure_user(email, nombre) for email, nombre in DEMO_USERS}
    pm = users["pm@center.demo"]

    auth = login(pm["email"])
    token = auth["access_token"]
    org_id = auth.get("organization_id")
    if not org_id:
        org = post(
            token,
            "/organizations",
            {"nombre": "Center Demo", "slug": "center-demo"},
        )
        org_id = org["id"]
        auth = login(pm["email"])
        token = auth["access_token"]

    portal_stats = seed_portal_cliente(token, org_id, today, users)
    interno_stats = seed_plataforma_interna(token, org_id, today, users)

    print(f"[seed] {SEED_VERSION} OK — {len(DEMO_USERS)} usuarios, {len(DEMO_PROJECTS)} proyectos")
    print(f"  • {portal_stats['project']['nombre']} (con_cliente):")
    print(
        f"      {portal_stats['milestones']} hitos, {portal_stats['features']} features, "
        f"{portal_stats['tasks']} tareas, {portal_stats['queries']} consultas, "
        f"{portal_stats['reports']} reportes"
    )
    print(f"  • {interno_stats['project']['nombre']} (interno):")
    print(
        f"      {interno_stats['milestones']} hitos, {interno_stats['features']} features, "
        f"{interno_stats['tasks']} tareas, {interno_stats['queries']} consultas"
    )
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
