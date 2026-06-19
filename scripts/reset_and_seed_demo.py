"""
Seed global Center v3: reset de BD + 4 proyectos demo.

Plantillas:
  • Portal Cliente Demo      — t1_cliente_clasico  (waterfall con cliente)
  • Plataforma Interna Center — t3_interno_clasico  (waterfall interno)
  • Logistics Hub            — t6_scrum_interno
  • E-commerce Relaunch      — t7_scrum_cliente

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
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "v3.db"
UPLOADS_DIR = DATA_DIR / "uploads"
BASE = os.environ.get("CENTER_API_BASE", "http://127.0.0.1:8000/api/v1")
DEMO_PASSWORD = "demo12345"
SEED_VERSION = "v13-global-four-templates"
# Procedimiento de wipe y smoke post-reset: docs/SMOKE_RESET_ROLES.md

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
    "Logistics Hub",
    "E-commerce Relaunch",
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
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {raw[:400]}") from e


TEAM_ROLE_SLUGS = ["pm", "dev", "qa", "tech_lead", "pm_tecnico"]


def visible_roles_for(visibilidad: str) -> list[str]:
    """Mapeo legacy visibilidad → visible_roles del hub (vacío = todos los roles)."""
    if visibilidad == "interno":
        return list(TEAM_ROLE_SLUGS)
    return []


def hub_entry_body(
    *,
    tipo: str,
    contenido: str,
    titulo: str | None = None,
    visibilidad: str = "publico",
    record_id: str | None = None,
) -> dict:
    body: dict = {
        "tipo": tipo,
        "contenido": contenido,
        "visible_roles": visible_roles_for(visibilidad),
    }
    if titulo:
        body["titulo"] = titulo
    if record_id:
        body["record_id"] = record_id
    return body


def wait_for_api(timeout_sec: int = 90) -> None:
    health_url = BASE.replace("/api/v1", "") + "/health"
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req, timeout=5) as res:
                if res.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"API no respondió en {health_url} — iniciá uvicorn en :8000")


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
    from app.database import SessionLocal
    from app.services.blocks import ensure_block_catalog
    from app.services.packs import ensure_system_packs

    with SessionLocal() as db:
        ensure_system_packs(db)
        ensure_block_catalog(db)
        db.commit()
    print(f"[reset] Tablas vaciadas en {DB_PATH} + catálogos re-seeded")


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
    try:
        return login(email)["user"]
    except RuntimeError:
        pass
    _, auth = http(
        "POST",
        "/auth/register",
        body={"email": email, "nombre": nombre, "password": DEMO_PASSWORD},
        expect_status=201,
    )
    return auth["user"]


def login(email: str) -> dict:
    _, auth = http(
        "POST",
        "/auth/login",
        body={"email": email, "password": DEMO_PASSWORD},
        expect_status=200,
    )
    return auth


def token_for_user(user_id: str, users: dict[str, dict], cache: dict[str, str]) -> str:
    if user_id in cache:
        return cache[user_id]
    for email, u in users.items():
        if u["id"] == user_id:
            cache[user_id] = login(email)["access_token"]
            return cache[user_id]
    raise KeyError(f"Usuario no encontrado: {user_id}")


def add_member(token: str, project_id: str, user_id: str, rol: str) -> None:
    try:
        http(
            "POST",
            f"/projects/{project_id}/members",
            body={"user_id": user_id, "rol": rol},
            token=token,
            expect_status=201,
        )
    except RuntimeError:
        pass


def post(token: str, path: str, body: dict, *, expect: int = 201) -> dict:
    _, data = http("POST", path, body=body, token=token, expect_status=expect)
    return data


def create_record_dependency(
    token: str,
    project_id: str,
    predecessor_id: str,
    successor_id: str,
) -> None:
    post(
        token,
        f"/projects/{project_id}/record-dependencies",
        {
            "predecessor_id": predecessor_id,
            "successor_id": successor_id,
        },
    )


def create_project(token: str, org_id: str, **kwargs) -> dict:
    kwargs.setdefault("organization_id", org_id)
    return post(token, "/projects", kwargs)


def create_milestone(
    token: str,
    project_id: str,
    *,
    nombre: str,
    orden: int,
    fecha_inicio: str,
    fecha_fin: str,
    descripcion: str = "",
) -> dict:
    body: dict = {
        "record_type": "milestone",
        "titulo": nombre,
        "descripcion": descripcion,
        "data": {"tipo": "entrega"},
        "orden": orden,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
    }
    return post(token, f"/projects/{project_id}/records", body)


def record_title(rec: dict) -> str:
    return str(rec.get("titulo") or rec.get("nombre") or "registro")


def create_feature(
    token: str,
    project_id: str,
    milestone_id: str,
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
        f"/projects/{project_id}/records",
        {
            "record_type": "feature",
            "titulo": nombre,
            "descripcion": descripcion,
            "parent_id": milestone_id,
            "initial_state": estado,
            "data": {"tipo": "desarrollo", "prioridad": prioridad, "bloqueada": False},
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
        },
    )


def create_task(
    token: str,
    project_id: str,
    _milestone_id: str,
    feature_id: str,
    *,
    titulo: str,
    estado: str,
    asignado_ids: list[str] | None = None,
    descripcion: str = "",
) -> dict:
    body: dict = {
        "record_type": "task",
        "titulo": titulo,
        "parent_id": feature_id,
        "initial_state": estado,
    }
    if asignado_ids:
        body["assignee_ids"] = asignado_ids
    if descripcion:
        body["descripcion"] = descripcion
    return post(token, f"/projects/{project_id}/records", body)


def transition_record(
    token: str,
    project_id: str,
    record_id: str,
    *,
    action_id: str,
    target_state: str | None = None,
    side_effect_context: dict | None = None,
    ignore_errors: bool = False,
) -> dict | None:
    body: dict = {"action_id": action_id}
    if target_state is not None:
        body["target_state"] = target_state
    if side_effect_context:
        body["side_effect_context"] = side_effect_context
    try:
        _, data = http(
            "POST",
            f"/projects/{project_id}/records/{record_id}/transition",
            body=body,
            token=token,
            expect_status=200,
        )
        return data
    except RuntimeError:
        if ignore_errors:
            return None
        raise


def create_query(
    token: str,
    project_id: str,
    feature_id: str,
    *,
    titulo: str,
    descripcion: str,
) -> dict:
    return post(
        token,
        f"/projects/{project_id}/records",
        {
            "record_type": "query",
            "titulo": titulo,
            "descripcion": descripcion,
            "parent_id": feature_id,
        },
    )


def create_report(
    token: str,
    project_id: str,
    feature_id: str,
    *,
    tipo: str,
    descripcion: str,
    reported_by: str,
) -> dict:
    return post(
        token,
        f"/projects/{project_id}/records",
        {
            "record_type": "report",
            "titulo": descripcion[:120],
            "descripcion": descripcion,
            "parent_id": feature_id,
            "data": {"tipo": tipo, "reported_by": reported_by},
        },
    )


def create_comment(
    token: str,
    *,
    entidad_tipo: str,
    entidad_id: str,
    contenido: str,
    estado_momento: str,
) -> None:
    post(
        token,
        "/comments",
        {
            "entidad_tipo": entidad_tipo,
            "entidad_id": entidad_id,
            "contenido": contenido,
            "estado_momento": estado_momento,
        },
    )


def seed_tasks_for_feature(
    project_id: str,
    milestone_id: str,
    feature_id: str,
    feature_nombre: str,
    dev_ids: list[str],
    users: dict[str, dict],
    token_cache: dict[str, str],
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
        dev_token = token_for_user(dev, users, token_cache)
        titulo = f"{prefixes[i % len(prefixes)]} {feature_nombre} #{i + 1}"
        create_task(
            dev_token,
            project_id,
            milestone_id,
            feature_id,
            titulo=titulo,
            estado=TASK_STATES[i % len(TASK_STATES)],
            asignado_ids=[dev] if i % 4 != 3 else None,
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
    token_cache: dict[str, str] = {pm["id"]: token}

    portal = create_project(
        token,
        org_id,
        nombre="Portal Cliente Demo",
        descripcion=(
            "Proyecto con cliente externo: inbox denso, reportes, consultas, "
            "hub, validación UAT y Kanban con muchas tareas."
        ),
        template_slug="t1_cliente_clasico",
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
        add_member(token, portal["id"], uid, rol)

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
            nombre=nombre,
            orden=orden,
            fecha_inicio=add_days(today, start),
            fecha_fin=add_days(today, end),
            descripcion=desc,
        )
        milestones.append(ms)

    transition_record(
        token,
        portal["id"],
        milestones[4]["id"],
        action_id="cancelar",
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
                portal["id"],
                milestones[ms_idx]["id"],
                feat["id"],
                nombre,
                dev_ids,
                users,
                token_cache,
                count=n_tasks,
            )

    auth_feat = features[0]
    oauth = features[2]
    webhooks = features[8]
    dashboard = features[1]
    api_publica = features[9]

    create_record_dependency(token, portal["id"], oauth["id"], dashboard["id"])
    create_record_dependency(token, portal["id"], auth_feat["id"], oauth["id"])
    create_record_dependency(token, portal["id"], webhooks["id"], api_publica["id"])

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
        q = create_query(
            token_for_user(author, users, token_cache),
            portal["id"],
            feat["id"],
            titulo=titulo,
            descripcion=desc,
        )
        actor = dev["id"] if action == "solicitar_envio" else pm["id"]
        transition_record(
            token_for_user(actor, users, token_cache),
            portal["id"],
            q["id"],
            action_id=action,
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
        create_report(
            token_for_user(cliente["id"], users, token_cache),
            portal["id"],
            feat["id"],
            tipo=tipo,
            descripcion=desc,
            reported_by=cliente["id"],
        )

    spec_contenido = (
        "Alcance MVP: auth, dashboard, OAuth, notificaciones.\n\n"
        "Integraciones: webhooks, Salesforce, API pública.\n\n"
        "Analytics y mobile web en entregas posteriores."
    )
    post(
        token,
        f"/projects/{portal['id']}/hub-entries",
        hub_entry_body(
            tipo="page",
            titulo="Especificación funcional Portal Cliente",
            contenido=spec_contenido,
            visibilidad="publico",
        ),
    )
    post(
        token,
        f"/projects/{portal['id']}/hub-entries",
        hub_entry_body(
            tipo="page",
            titulo="Alcance Entrega 1 — MVP",
            contenido="Detalle de alcance para la primera entrega (MVP).",
            visibilidad="publico",
            record_id=milestones[0]["id"],
        ),
    )
    post(
        token,
        f"/projects/{portal['id']}/hub-entries",
        hub_entry_body(
            tipo="page",
            titulo="Webhooks — anexo técnico",
            contenido="Contratos y ejemplos de payload para webhooks salientes.",
            visibilidad="publico",
            record_id=webhooks["id"],
        ),
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
            token_for_user(author, users, token_cache),
            f"/projects/{portal['id']}/hub-entries",
            hub_entry_body(tipo="update", contenido=contenido, visibilidad=vis),
        )
    for titulo, contenido, author, vis in hub_notes:
        post(
            token_for_user(author, users, token_cache),
            f"/projects/{portal['id']}/hub-entries",
            hub_entry_body(
                tipo="note",
                titulo=titulo,
                contenido=contenido,
                visibilidad=vis,
            ),
        )

    for i, feat in enumerate(features[:12]):
        create_comment(
            token_for_user(dev_ids[i % 2], users, token_cache),
            entidad_tipo="feature",
            entidad_id=feat["id"],
            contenido=f"Comentario demo #{i + 1} en {record_title(feat)[:40]}.",
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
    token_cache: dict[str, str] = {pm["id"]: token}

    interno = create_project(
        token,
        org_id,
        nombre="Plataforma Interna Center",
        descripcion=(
            "Proyecto interno: múltiples sprints, UAT denso, consultas PM, "
            "hub interno y Kanban con decenas de tareas."
        ),
        template_slug="t3_interno_clasico",
        fecha_inicio=add_days(today, -30),
        fecha_fin=add_days(today, 90),
    )
    for uid, rol in [
        (pm["id"], "pm"),
        (dev["id"], "dev"),
        (dev2["id"], "dev"),
        (qa["id"], "qa"),
    ]:
        add_member(token, interno["id"], uid, rol)

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
                interno["id"],
                milestones[ms_idx]["id"],
                feat["id"],
                nombre,
                dev_ids,
                users,
                token_cache,
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
        q = create_query(
            token_for_user(author, users, token_cache),
            interno["id"],
            feat["id"],
            titulo=titulo,
            descripcion=desc,
        )
        transition_record(
            token,
            interno["id"],
            q["id"],
            action_id="activar",
        )

    post(
        token,
        f"/projects/{interno['id']}/hub-entries",
        hub_entry_body(
            tipo="page",
            titulo="Wiki técnica Plataforma Interna",
            contenido=(
                "Contratos API, ADRs, runbooks y checklists de release.\n\n"
                "Solo visible para el equipo (roles internos)."
            ),
            visibilidad="interno",
        ),
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
            token_for_user(author, users, token_cache),
            f"/projects/{interno['id']}/hub-entries",
            hub_entry_body(tipo="update", contenido=contenido, visibilidad="interno"),
        )

    for titulo, contenido, author in [
        ("Convención commits", "Conventional commits + scope.", pm["id"]),
        ("Deuda Q3", "Migración PG y cache Redis.", dev["id"]),
        ("QA focus", "UAT gates por feature.", pm["id"]),
    ]:
        post(
            token_for_user(author, users, token_cache),
            f"/projects/{interno['id']}/hub-entries",
            hub_entry_body(
                tipo="note",
                titulo=titulo,
                contenido=contenido,
                visibilidad="interno",
            ),
        )

    for i, feat in enumerate(features):
        create_comment(
            token_for_user(dev_ids[i % 2], users, token_cache),
            entidad_tipo="feature",
            entidad_id=feat["id"],
            contenido=f"Seguimiento interno #{i + 1}: {record_title(feat)[:35]}.",
            estado_momento=features_spec[i][2],
        )

    return {
        "project": interno,
        "milestones": len(milestones),
        "features": len(features),
        "tasks": task_total,
        "queries": len(queries_spec),
    }

# ── Scrum demo (t6 + t7) ────────────────────────────────────────────────────

HistoriaSpec = tuple[str, str, str, str, list[float] | None]

# (nombre, orden, start_offset, end_offset, goal, sprint_state, velocidad_planeada)
SprintDef = tuple[str, int, int, int, str, str, int]

SPRINTS: list[SprintDef] = [
    (
        "Sprint 1 — Fundamentos",
        1,
        -56,
        -43,
        "Modelo de almacenes, SKUs y API de inventario con UI operativa.",
        "completado",
        34,
    ),
    (
        "Sprint 2 — Operaciones",
        2,
        -14,
        -1,
        "Recepciones, movimientos de stock y alertas de mínimos.",
        "en_progreso",
        31,
    ),
    (
        "Sprint 3 — Tracking",
        3,
        0,
        13,
        "Trazabilidad de envíos, estados en tiempo real y notificaciones.",
        "pendiente",
        28,
    ),
    (
        "Sprint 4 — Analytics",
        4,
        14,
        27,
        "Dashboards de rotación, SLA de entrega y exportaciones.",
        "pendiente",
        30,
    ),
]

S1_SPEC: list[HistoriaSpec] = [
    ("Modelo de almacenes y SKUs", "8", "alta", "completado", [4, 4, 2]),
    ("API CRUD inventario", "5", "alta", "completado", [3, 3, 2]),
    ("UI: lista de stock con filtros", "5", "alta", "completado", [3, 2, 2]),
    ("Importación masiva CSV de productos", "3", "media", "completado", [2, 2]),
    ("Tests integración capa repositorio", "3", "media", "completado", [2, 1.5]),
    ("Documentación API inventario (OpenAPI)", "2", "baja", "completado", [1.5, 1]),
]

S2_SPEC: list[HistoriaSpec] = [
    ("Recepción de mercadería con lote", "8", "alta", "uat", [4, 4, 2]),
    ("Movimientos entre almacenes", "5", "alta", "en_progreso", [3, 3, 2]),
    ("Alertas de stock mínimo por SKU", "5", "media", "en_progreso", [2.5, 2.5, 2]),
    ("Historial de movimientos auditables", "3", "media", "esperando_liberacion_pm", [2, 2]),
    ("Reserva de stock para pedidos", "5", "alta", "pendiente", [3, 3]),
    ("UI: panel de operaciones diarias", "3", "media", "pendiente", [2, 1.5]),
]

S3_SPEC: list[HistoriaSpec] = [
    ("Estados de envío y timeline", "8", "alta", "pendiente", [4, 4, 2]),
    ("Tracking por código de seguimiento", "5", "alta", "pendiente", [3, 3]),
    ("Notificaciones email en hitos clave", "5", "media", "pendiente", [2.5, 2.5]),
    ("Webhook para integraciones TMS", "3", "media", "pendiente", [2, 2]),
    ("Mapa de rutas activas (vista lista)", "3", "baja", "pendiente", [2, 1.5]),
]

S4_SPEC: list[HistoriaSpec] = [
    ("Dashboard rotación de inventario", "8", "alta", "pendiente", None),
    ("SLA de entrega por carrier", "5", "alta", "pendiente", None),
    ("Export CSV de métricas semanales", "3", "media", "pendiente", None),
    ("Gráficos de incidencias por hub", "5", "media", "pendiente", None),
    ("Reporte de fill-rate por almacén", "3", "baja", "pendiente", None),
]

SPRINT_HISTORIAS: dict[int, list[HistoriaSpec]] = {
    1: S1_SPEC,
    2: S2_SPEC,
    3: S3_SPEC,
    4: S4_SPEC,
}

# (titulo, story_points, prioridad, horas_tareas | None)
BACKLOG: list[tuple[str, str, str, list[float] | None]] = [
    ("Integración ERP SAP (inventario)", "13", "alta", [8, 6]),
    ("App móvil escaneo de códigos de barras", "8", "alta", [6, 4]),
    ("Optimización de rutas con ML", "13", "media", None),
    ("Multi-tenant para 3PL", "8", "alta", [4, 4]),
    ("Portal cliente: tracking self-service", "5", "media", [3, 2]),
    ("Gestión de devoluciones (RMA)", "5", "media", [3, 2.5]),
    ("Etiquetado ZPL para impresoras térmicas", "3", "baja", [2, 1.5]),
    ("Control de temperatura cadena frío", "8", "baja", None),
    ("API GraphQL para partners", "5", "baja", None),
    ("Automatización reabastecimiento predictivo", "13", "media", None),
]

TASK_TITLES = [
    "Análisis y diseño",
    "Implementación backend",
    "Implementación frontend",
    "Tests y revisión",
]


# ── Seed principal ────────────────────────────────────────────────────────────


def mk_sprint(token, pid, *, nombre, orden, fi, ff, goal, horas_planeadas):
    return post(token, f"/projects/{pid}/records", {
        "record_type": "sprint",
        "titulo": nombre,
        "descripcion": goal,
        "data": {
            "sprint_goal": goal,
            "horas_planeadas": horas_planeadas,
        },
        "orden": orden,
        "fecha_inicio": fi,
        "fecha_fin": ff,
    })


def mk_epic(token, pid, *, nombre):
    return post(token, f"/projects/{pid}/records", {
        "record_type": "task",
        "titulo": nombre,
        "data": {"scrum_role": "epic"},
    })


def mk_historia(token, pid, *, nombre, epic_id, prio, desc=""):
    return post(token, f"/projects/{pid}/records", {
        "record_type": "task",
        "titulo": nombre,
        "descripcion": desc,
        "initial_state": "product_backlog",
        "data": {
            "scrum_role": "story",
            "epic_task_id": epic_id,
            "prioridad": prio,
            "bloqueada": False,
        },
    })


def mk_backlog(token, pid, *, nombre, epic_id, prio, desc=""):
    return mk_historia(token, pid, nombre=nombre, epic_id=epic_id, prio=prio, desc=desc)


def mk_tarea(token, pid, story_id, *, titulo, estado, asignee=None, horas=None):
    body = {
        "record_type": "task",
        "titulo": titulo,
        "data": {
            "scrum_role": "dev",
            "parent_task_id": story_id,
        },
        "initial_state": estado,
    }
    if horas is not None:
        body["data"]["estimacion_horas"] = horas
    if asignee:
        body["assignee_ids"] = [asignee]
    return post(token, f"/projects/{pid}/records", body)


def mk_subtarea(token, pid, parent_dev_id, *, titulo, estado, asignee=None, horas=None):
    body = {
        "record_type": "task",
        "titulo": titulo,
        "data": {
            "scrum_role": "dev",
            "parent_task_id": parent_dev_id,
        },
        "initial_state": estado,
    }
    if horas is not None:
        body["data"]["estimacion_horas"] = horas
    if asignee:
        body["assignee_ids"] = [asignee]
    return post(token, f"/projects/{pid}/records", body)


def seed_subtareas(token, pid, parent_dev_id, *, asignee=None, count: int = 2):
    estados = ["to_do", "in_progress", "completed"]
    for i in range(count):
        mk_subtarea(
            token, pid, parent_dev_id,
            titulo=f"Subtarea {i + 1}",
            estado=estados[i % len(estados)],
            asignee=asignee,
            horas=1.5 + i,
        )


def seed_tareas(
    token,
    pid,
    feature_id,
    horas_list,
    *,
    asignee=None,
    task_estado=None,
):
    estados_cycle = ["to_do", "in_progress", "completed", "ready_for_test"]
    for i, horas in enumerate(horas_list):
        titulo = TASK_TITLES[i % len(TASK_TITLES)]
        if len(horas_list) > len(TASK_TITLES):
            titulo = f"{titulo} ({i + 1})"
        estado = task_estado or estados_cycle[i % len(estados_cycle)]
        task = mk_tarea(
            token, pid, feature_id,
            titulo=titulo,
            estado=estado,
            asignee=asignee,
            horas=horas,
        )
        if i == 0 and len(horas_list) >= 2:
            seed_subtareas(token, pid, task["id"], asignee=asignee, count=2)


def task_estado_for_final(estado_final: str) -> str | None:
    if estado_final in ("completado", "uat", "esperando_liberacion_pm", "esperando_validacion_cliente"):
        return "ready_for_test"
    if estado_final == "pendiente":
        return "to_do"
    return None


def advance_historia(
    users,
    token_cache,
    pid,
    pm_id,
    tech_id,
    qa_id,
    feature_id,
    sprint_id,
    estado_final: str,
    *,
    horas_list: list[float] | None = None,
    assignee=None,
    task_estado: str | None = None,
):
    pm_token = token_for_user(pm_id, users, token_cache)
    tech_token = token_for_user(tech_id, users, token_cache)
    qa_token = token_for_user(qa_id, users, token_cache)
    scrum_tr(
        pm_token, pid, feature_id, action="comprometer_sprint",
        side_effect_context={"sprint_id": sprint_id},
    )
    if horas_list:
        seed_tareas(
            tech_token, pid, feature_id, horas_list,
            asignee=assignee,
            task_estado=task_estado or task_estado_for_final(estado_final),
        )
    if estado_final == "completado":
        scrum_tr(tech_token, pid, feature_id, action="pasar_a_uat")
        scrum_tr(qa_token, pid, feature_id, action="enviar_al_pm")
        scrum_tr(pm_token, pid, feature_id, action="completar")
    elif estado_final in ("uat", "esperando_liberacion_pm"):
        scrum_tr(tech_token, pid, feature_id, action="pasar_a_uat")
        if estado_final == "esperando_liberacion_pm":
            scrum_tr(qa_token, pid, feature_id, action="enviar_al_pm")


def scrum_tr(token, pid, rid, *, action, target=None, side_effect_context=None, silent=True):
    return transition_record(
        token, pid, rid,
        action_id=action,
        target_state=target,
        side_effect_context=side_effect_context,
        ignore_errors=silent,
    )


def scrum_hub_note(token, pid, *, titulo, contenido, visibilidad="interno"):
    return post(
        token,
        f"/projects/{pid}/hub-entries",
        hub_entry_body(tipo="note", titulo=titulo, contenido=contenido, visibilidad=visibilidad),
    )


def scrum_hub_update(token, pid, *, contenido, visibilidad="publico"):
    return post(
        token,
        f"/projects/{pid}/hub-entries",
        hub_entry_body(tipo="update", contenido=contenido, visibilidad=visibilidad),
    )

def seed_logistics_hub(token, users, org_id, today: date) -> dict[str, int | str]:

    pm = users["pm@center.demo"]
    tech = users["dev@center.demo"]
    dev = users["dev2@center.demo"]
    qa = users["qa@center.demo"]
    pm_id = pm["id"]
    token_cache: dict[str, str] = {pm_id: token}

    print("  Creando Logistics Hub (t6_scrum_interno)...")
    p = post(token, "/projects", {
        "organization_id": org_id,
        "nombre": "Logistics Hub",
        "descripcion": (
            "Plataforma de operaciones logísticas: inventario multi-almacén, "
            "movimientos, tracking de envíos y analíticas de rendimiento."
        ),
        "pack_slug": "software",
        "template_slug": "t6_scrum_interno",
        "fecha_inicio": add_days(today, -56),
        "fecha_fin": add_days(today, 84),
    })
    pid = p["id"]

    for uid, rol in [(pm_id, "pm"), (tech["id"], "tech_lead"), (dev["id"], "dev"), (qa["id"], "qa")]:
        add_member(token, pid, uid, rol)

    assignees = [tech["id"], dev["id"]]
    historia_count = 0
    task_count = 0

    epics = {
        "inventario": mk_epic(token, pid, nombre="Inventario")["id"],
        "operaciones": mk_epic(token, pid, nombre="Operaciones")["id"],
        "tracking": mk_epic(token, pid, nombre="Tracking")["id"],
        "analytics": mk_epic(token, pid, nombre="Analytics")["id"],
        "plataforma": mk_epic(token, pid, nombre="Plataforma")["id"],
    }
    epic_by_sprint = {
        1: epics["inventario"],
        2: epics["operaciones"],
        3: epics["tracking"],
        4: epics["analytics"],
    }

    for nombre, orden, start_off, end_off, goal, sprint_state, horas_plan in SPRINTS:
        sprint = mk_sprint(
            token, pid,
            nombre=nombre,
            orden=orden,
            fi=add_days(today, start_off),
            ff=add_days(today, end_off),
            goal=goal,
            horas_planeadas=horas_plan,
        )
        if sprint_state == "en_progreso":
            scrum_tr(token, pid, sprint["id"], action="sync", target="en_progreso")

        specs = SPRINT_HISTORIAS[orden]
        epic_id = epic_by_sprint.get(orden, epics["plataforma"])
        for idx, (titulo, _sp, prio, estado_final, horas_list) in enumerate(specs):
            h = mk_historia(
                token, pid,
                nombre=titulo,
                epic_id=epic_id,
                prio=prio,
            )
            historia_count += 1
            assignee = assignees[idx % len(assignees)]
            if horas_list:
                task_count += len(horas_list)

            advance_historia(
                users, token_cache, pid, pm_id, tech["id"], qa["id"], h["id"], sprint["id"], estado_final,
                horas_list=horas_list,
                assignee=assignee,
            )

        if sprint_state == "completado":
            scrum_tr(token, pid, sprint["id"], action="sync", target="completado")

    backlog_count = 0
    backlog_epics = [epics["plataforma"], epics["tracking"], epics["analytics"], epics["operaciones"]]
    for idx, (titulo, _sp, prio, horas_list) in enumerate(BACKLOG):
        epic_id = backlog_epics[idx % len(backlog_epics)]
        h = mk_backlog(token, pid, nombre=titulo, epic_id=epic_id, prio=prio)
        backlog_count += 1
        if horas_list:
            seed_tareas(
                token_for_user(tech["id"], users, token_cache), pid, h["id"], horas_list,
                asignee=assignees[idx % len(assignees)],
                task_estado="to_do",
            )
            task_count += len(horas_list)

    scrum_hub_update(token, pid, contenido="Sprint 1 completado. Inventario base operativo en staging.")
    scrum_hub_note(token, pid,
        titulo="Retro Sprint 1 — Fundamentos",
        contenido=(
            "**Bien:** Modelo de datos sólido; import CSV superó expectativas de volumen.\n\n"
            "**Mejorar:** Tests de integración tardaron; reservar buffer en Sprint 2.\n\n"
            "**Acción:** Documentar convenciones de SKU antes del grooming de operaciones."
        ),
    )
    scrum_hub_note(token, pid,
        titulo="Sprint 2 — Definition of Done",
        contenido=(
            "Historia Done cuando:\n"
            "- Código mergeado y revisado\n"
            "- Movimientos auditables con trazabilidad\n"
            "- QA en staging sin blockers\n"
            "- Alertas de mínimos validadas con datos reales"
        ),
    )
    scrum_hub_update(token_for_user(tech["id"], users, token_cache), pid,
        contenido="Recepción de mercadería en UAT. Movimientos entre almacenes ~70% front.")
    scrum_hub_update(token_for_user(dev["id"], users, token_cache), pid,
        contenido="Grooming Sprint 3: estimación tracking y webhooks TMS el jueves.")
    scrum_hub_note(token, pid,
        titulo="Planning Sprint 3 y 4",
        contenido=(
            "Sprint 3 foco en tracking visible para operaciones.\n"
            "Sprint 4 reservado para analytics; no iniciar tareas hasta cerrar S3.\n"
            "Velocity objetivo S3: 28h · S4: 30h."
        ),
    )

    return {
        "project_id": pid,
        "sprints": len(SPRINTS),
        "historias_sprint": historia_count,
        "backlog": backlog_count,
        "tasks": task_count,
    }


def seed_ecommerce(token_pm, token_cliente, users, org_id, today):
    pm = users["pm@center.demo"]
    tech = users["dev@center.demo"]
    dev = users["dev2@center.demo"]
    qa = users["qa@center.demo"]
    cliente = users["cliente@center.demo"]
    pm_id = pm["id"]

    token_cache: dict[str, str] = {
        pm_id: token_pm,
        cliente["id"]: token_cliente,
    }

    print("  Creando E-commerce Relaunch (t7_scrum_cliente)...")
    p = post(token_pm, "/projects", {
        "organization_id": org_id,
        "nombre": "E-commerce Relaunch",
        "descripcion": "Rediseno completo del ecommerce. Catalogo, carrito, checkout y panel de cliente.",
        "pack_slug": "software",
        "template_slug": "t7_scrum_cliente",
        "fecha_inicio": add_days(today, -42),
        "fecha_fin": add_days(today, 98),
    })
    pid = p["id"]

    for uid, rol in [
        (pm_id, "pm"), (tech["id"], "tech_lead"),
        (dev["id"], "dev"), (qa["id"], "qa"),
        (cliente["id"], "cliente"),
    ]:
        add_member(token_pm, pid, uid, rol)

    epics = {
        "catalogo": mk_epic(token_pm, pid, nombre="Catálogo")["id"],
        "checkout": mk_epic(token_pm, pid, nombre="Checkout")["id"],
        "cliente": mk_epic(token_pm, pid, nombre="Panel cliente")["id"],
        "plataforma": mk_epic(token_pm, pid, nombre="Plataforma")["id"],
    }

    s1 = mk_sprint(token_pm, pid,
        nombre="Sprint 1 — Catalogo de productos",
        orden=1,
        fi=add_days(today, -42),
        ff=add_days(today, -29),
        goal="Catalogo publico con filtros, busqueda y detalle de producto.",
        horas_planeadas=32,
    )
    s1_spec = [
        ("Pagina de catalogo con grilla de productos", "alta", [4, 4]),
        ("Filtros por categoria, precio y disponibilidad", "alta", [2.5, 2.5]),
        ("Pagina de detalle de producto con galeria", "alta", [4, 4]),
        ("Busqueda por nombre y descripcion", "media", [2.5, 2.5]),
    ]
    for nombre, prio, horas_list in s1_spec:
        h = mk_historia(token_pm, pid, nombre=nombre, epic_id=epics["catalogo"], prio=prio)
        scrum_tr(token_pm, pid, h["id"], action="comprometer_sprint", side_effect_context={"sprint_id": s1["id"]})
        seed_tareas(token_for_user(tech["id"], users, token_cache), pid, h["id"], horas_list, asignee=tech["id"], task_estado="ready_for_test")
        scrum_tr(token_for_user(tech["id"], users, token_cache), pid, h["id"], action="pasar_a_uat")
        scrum_tr(token_for_user(qa["id"], users, token_cache), pid, h["id"], action="enviar_al_pm")
        scrum_tr(token_pm, pid, h["id"], action="liberar_cliente")
        scrum_tr(token_cliente, pid, h["id"], action="confirmar")
    scrum_tr(token_pm, pid, s1["id"], action="sync", target="completado")

    s2 = mk_sprint(token_pm, pid,
        nombre="Sprint 2 — Carrito y checkout",
        orden=2,
        fi=add_days(today, -14),
        ff=add_days(today, -1),
        goal="Flujo completo de compra: agregar al carrito, checkout, pago y confirmacion de pedido.",
        horas_planeadas=28,
    )
    scrum_tr(token_pm, pid, s2["id"], action="sync", target="en_progreso")

    s2_spec = [
        ("Carrito persistente (localStorage + API)", "alta", "esperando_validacion_cliente", [2.5, 2.5]),
        ("Checkout: datos de envio y resumen", "alta", "esperando_liberacion_pm", [4, 4]),
        ("Integracion con pasarela de pago (Stripe)", "alta", "uat", [4, 4]),
        ("Pagina de confirmacion y email transaccional", "media", "en_progreso", [2.5, 2.5]),
        ("Validaciones de stock en checkout", "media", "pendiente", [1.5, 1.5]),
    ]
    for nombre, prio, estado_final, horas_list in s2_spec:
        h = mk_historia(token_pm, pid, nombre=nombre, epic_id=epics["checkout"], prio=prio)
        scrum_tr(token_pm, pid, h["id"], action="comprometer_sprint", side_effect_context={"sprint_id": s2["id"]})
        task_estado = (
            "ready_for_test"
            if estado_final in ("uat", "esperando_liberacion_pm", "esperando_validacion_cliente")
            else None
        )
        seed_tareas(token_for_user(tech["id"], users, token_cache), pid, h["id"], horas_list, asignee=dev["id"], task_estado=task_estado)
        if estado_final in ("uat", "esperando_liberacion_pm", "esperando_validacion_cliente"):
            scrum_tr(token_for_user(tech["id"], users, token_cache), pid, h["id"], action="pasar_a_uat")
        if estado_final in ("esperando_liberacion_pm", "esperando_validacion_cliente"):
            scrum_tr(token_for_user(qa["id"], users, token_cache), pid, h["id"], action="enviar_al_pm")
        if estado_final == "esperando_validacion_cliente":
            scrum_tr(token_pm, pid, h["id"], action="liberar_cliente")

    s3 = mk_sprint(token_pm, pid,
        nombre="Sprint 3 — Panel de cliente",
        orden=3,
        fi=add_days(today, 0),
        ff=add_days(today, 13),
        goal="Historial de pedidos, estado en tiempo real y gestion de direcciones del cliente.",
        horas_planeadas=26,
    )
    s3_spec = [
        ("Historial de pedidos con filtros", "alta", [4, 4]),
        ("Estado de pedido en tiempo real (polling)", "alta", [2.5, 2.5]),
        ("Gestion de direcciones de envio", "media", [2.5, 2.5]),
        ("Descarga de factura en PDF", "baja", [1.5, 1.5]),
    ]
    for nombre, prio, horas_list in s3_spec:
        h = mk_historia(token_pm, pid, nombre=nombre, epic_id=epics["cliente"], prio=prio)
        scrum_tr(token_pm, pid, h["id"], action="comprometer_sprint", side_effect_context={"sprint_id": s3["id"]})
        seed_tareas(token_for_user(tech["id"], users, token_cache), pid, h["id"], horas_list, asignee=dev["id"])

    backlog_ec = [
        ("Panel de administracion de productos", "alta", [6, 4]),
        ("Wishlist / lista de deseos", "media", [3, 2]),
        ("Reviews y valoraciones de productos", "media", [4, 4]),
        ("Programa de puntos y fidelizacion", "baja", [8]),
        ("Integracion con ERP de inventario", "alta", None),
        ("App movil con React Native", "baja", None),
    ]
    backlog_epics = [epics["plataforma"], epics["catalogo"], epics["checkout"], epics["cliente"]]
    for idx, (nombre, prio, horas_list) in enumerate(backlog_ec):
        epic_id = backlog_epics[idx % len(backlog_epics)]
        h = mk_backlog(token_pm, pid, nombre=nombre, epic_id=epic_id, prio=prio)
        if horas_list:
            seed_tareas(token_for_user(tech["id"], users, token_cache), pid, h["id"], horas_list, asignee=dev["id"])

    scrum_hub_update(token_pm, pid, contenido="Sprint 1 cerrado. Catalogo live en staging, aprobado por cliente.")
    scrum_hub_note(token_pm, pid,
        titulo="Feedback cliente — Sprint 1",
        contenido=(
            "El cliente solicita:\n"
            "- Filtro por marca en el catalogo (P2)\n"
            "- Galeria con zoom en detalle de producto (P1)\n\n"
            "El zoom se agrega como historia en el backlog. El filtro por marca en Sprint 2 si hay capacidad."
        ),
    )
    scrum_hub_note(token_pm, pid,
        titulo="Sprint 2 — Riesgos",
        contenido=(
            "**Integracion Stripe:** Primera vez que el equipo trabaja con esta API. "
            "Tech Lead investigara docs 1 dia antes de estimar tareas.\n\n"
            "**Buffer de QA:** Checkout requiere pruebas E2E en distintos browsers. "
            "Reservar 2 dias extra para QA en la segunda semana del sprint."
        ),
    )
    scrum_hub_update(token_for_user(tech["id"], users, token_cache), pid,
        contenido="Carrito validado por cliente. Checkout en UAT, pendiente aprobacion del PM.")
    scrum_hub_update(token_pm, pid,
        contenido="Feedback del cliente: Carrito funciona bien en desktop. Pendiente prueba en mobile.")

    print(f"  [OK] E-commerce Relaunch — id: {pid}")
    return pid


def sync_sprint_velocity(token: str, project_id: str, sprint_id: str) -> None:
    path = f"/projects/{project_id}/scrum/sprints/{sprint_id}/sync-velocity"
    http("POST", path, token=token, expect_status=200)


def seed_scrum_support_data(
    token: str,
    project_id: str,
    pm_id: str,
    users: dict[str, dict],
) -> None:
    sprints = http(
        "GET",
        f"/projects/{project_id}/scrum/sprints",
        token=token,
    )[1] or []
    if not sprints:
        return
    sprint = next((s for s in sprints if s.get("estado") != "completado"), sprints[0])
    sprint_id = sprint["id"]
    dev_id = users.get("dev@center.demo", {}).get("id")
    qa_id = users.get("qa@center.demo", {}).get("id")

    capacity_plan = [
        {"user_id": pm_id, "dias": 8, "pto_dias": 6, "focus_pct": 65, "committed_h": 31.2},
        {"user_id": dev_id, "dias": 8, "pto_dias": 6.5, "focus_pct": 75, "committed_h": 39.0},
        {"user_id": qa_id, "dias": 6, "pto_dias": 5.5, "focus_pct": 70, "committed_h": 23.1},
    ]
    http(
        "PUT",
        f"/projects/{project_id}/scrum/sprints/{sprint_id}/capacity",
        token=token,
        body={"capacity_plan": capacity_plan},
        expect_status=200,
    )

    impediments = [
        {
            "titulo": "Ambiente staging inestable",
            "owner_user_id": dev_id,
            "impacto": "Bloquea validaciones de integración en historias checkout.",
        },
        {
            "titulo": "Proveedor de pagos demora respuesta",
            "owner_user_id": pm_id,
            "impacto": "Riesgo para cerrar objetivo del sprint actual.",
        },
    ]
    created_imps: list[dict] = []
    for item in impediments:
        _, imp = http(
            "POST",
            f"/projects/{project_id}/scrum/impediments",
            token=token,
            body={
                "titulo": item["titulo"],
                "sprint_id": sprint_id,
                "owner_user_id": item["owner_user_id"],
                "impacto": item["impacto"],
            },
            expect_status=200,
        )
        created_imps.append(imp)
    if created_imps:
        http(
            "POST",
            f"/projects/{project_id}/scrum/impediments/{created_imps[0]['id']}/resolve",
            token=token,
            body={"resolucion": "Reinicio de pods + ventana de validación coordinada."},
            expect_status=200,
        )

    sessions = [
        ("daily", "Daily de seguimiento", "active"),
        ("planning_poker", "Planning Poker (horas)", "planned"),
        ("sprint_review", "Sprint Review semanal", "planned"),
        ("retro", "Retro del sprint", "planned"),
    ]
    for session_type, title, status in sessions:
        _, session = http(
            "POST",
            f"/projects/{project_id}/scrum/sessions",
            token=token,
            body={
                "session_type": session_type,
                "title": title,
                "status": status,
                "sprint_id": sprint_id,
            },
            expect_status=200,
        )
        if session_type == "planning_poker":
            for hours in [2, 3, 5]:
                http(
                    "POST",
                    f"/projects/{project_id}/scrum/sessions/{session['id']}/entries",
                    token=token,
                    body={
                        "entry_type": "vote",
                        "payload": {"hours": hours, "story_hint": "Checkout mobile"},
                    },
                    expect_status=200,
                )
        else:
            http(
                "POST",
                f"/projects/{project_id}/scrum/sessions/{session['id']}/entries",
                token=token,
                body={
                    "entry_type": "note",
                    "payload": {"text": f"Nota inicial para {title.lower()}"},
                },
                expect_status=200,
            )


def seed_scrum_projects(
    token: str,
    token_cliente: str,
    org_id: str,
    today: date,
    users: dict[str, dict],
    pm_id: str,
) -> dict:
    """Sembrar Logistics Hub (t6) y E-commerce Relaunch (t7)."""
    print("\n[seed] Proyectos Scrum (t6 + t7)...")
    lh_stats = seed_logistics_hub(token, users, org_id, today)
    logistics_id = lh_stats["project_id"]
    seed_scrum_support_data(token, logistics_id, pm_id, users)

    sprints = http("GET", f"/projects/{logistics_id}/scrum/sprints", token=token)[1]
    if sprints:
        s1 = next((s for s in sprints if s.get("orden") == 1), sprints[0])
        try:
            sync_sprint_velocity(token, logistics_id, s1["id"])
        except RuntimeError as exc:
            print(f"  [warn] sync velocity Logistics: {exc}")

    ecommerce_id = seed_ecommerce(token, token_cliente, users, org_id, today)
    seed_scrum_support_data(token, ecommerce_id, pm_id, users)

    return {
        "logistics": lh_stats,
        "ecommerce_id": ecommerce_id,
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

    token_cliente = login("cliente@center.demo")["access_token"]

    portal_stats = seed_portal_cliente(token, org_id, today, users)
    interno_stats = seed_plataforma_interna(token, org_id, today, users)
    scrum_stats = seed_scrum_projects(
        token, token_cliente, org_id, today, users, pm["id"],
    )
    lh = scrum_stats["logistics"]

    print(f"[seed] {SEED_VERSION} OK — {len(DEMO_USERS)} usuarios, {len(DEMO_PROJECTS)} proyectos")
    print(f"  • {portal_stats['project']['nombre']} (t1_cliente_clasico):")
    print(
        f"      {portal_stats['milestones']} hitos, {portal_stats['features']} features, "
        f"{portal_stats['tasks']} tareas, {portal_stats['queries']} consultas, "
        f"{portal_stats['reports']} reportes"
    )
    print(f"  • {interno_stats['project']['nombre']} (t3_interno_clasico):")
    print(
        f"      {interno_stats['milestones']} hitos, {interno_stats['features']} features, "
        f"{interno_stats['tasks']} tareas, {interno_stats['queries']} consultas"
    )
    print("  • Logistics Hub (t6_scrum_interno):")
    print(
        f"      {lh['sprints']} sprints, {lh['historias_sprint']} historias en sprint, "
        f"{lh['backlog']} backlog, {lh['tasks']} tareas dev"
    )
    print(f"  • E-commerce Relaunch (t7_scrum_cliente): id={scrum_stats['ecommerce_id']}")
    print("  Cuentas: " + ", ".join(e for e, _ in DEMO_USERS))
    print(f"  Password: {DEMO_PASSWORD}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset + seed demo Center v3 (4 plantillas)")
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
