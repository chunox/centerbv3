"""
Crea un proyecto Scrum demo con sprints, historias, tareas y entradas de hub.

Uso (con API en :8000 y usuarios demo existentes):
  .venv\\Scripts\\python.exe scripts/seed_scrum_demo.py

Requiere que los usuarios demo ya existan (reset_and_seed_demo.py los crea).
No borra ni reinicia la BD.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000/api/v1"
DEMO_PASSWORD = "demo12345"


# ── HTTP ──────────────────────────────────────────────────────────────────────

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
        with urllib.request.urlopen(req, timeout=30) as res:
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


def post(token: str, path: str, body: dict, *, expect: int = 201) -> dict:
    _, data = http("POST", path, body=body, token=token, expect_status=expect)
    return data


# ── Auth y usuarios ───────────────────────────────────────────────────────────

def login(email: str) -> dict:
    _, auth = http(
        "POST",
        "/auth/login",
        body={"email": email, "password": DEMO_PASSWORD},
        expect_status=200,
    )
    return auth


def get_users() -> dict[str, dict]:
    _, users = http("GET", "/users")
    return {u["email"]: u for u in users}


def add_member(token: str, project_id: str, pm_id: str, user_id: str, rol: str) -> None:
    try:
        post(
            token,
            f"/projects/{project_id}/members",
            {"actor_user_id": pm_id, "user_id": user_id, "rol": rol},
            expect=201,
        )
    except RuntimeError:
        pass


# ── Helpers de fecha ──────────────────────────────────────────────────────────

def add_days(base: date, days: int) -> str:
    return (base + timedelta(days=days)).isoformat()


# ── Creación de registros ─────────────────────────────────────────────────────

def create_sprint(
    token: str,
    project_id: str,
    pm_id: str,
    *,
    nombre: str,
    orden: int,
    fecha_inicio: str,
    fecha_fin: str,
    sprint_goal: str,
    velocidad_planeada: int,
) -> dict:
    return post(
        token,
        f"/projects/{project_id}/records",
        {
            "actor_user_id": pm_id,
            "record_type": "milestone",
            "titulo": nombre,
            "descripcion": sprint_goal,
            "data": {
                "tipo": "entrega",
                "sprint_goal": sprint_goal,
                "velocidad_planeada": velocidad_planeada,
            },
            "orden": orden,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
        },
    )


def create_historia(
    token: str,
    project_id: str,
    pm_id: str,
    *,
    nombre: str,
    sprint_id: str | None,
    story_points: str,
    prioridad: str,
    estado_inicial: str,
    fecha_inicio: str,
    fecha_fin: str,
    descripcion: str = "",
) -> dict:
    return post(
        token,
        f"/projects/{project_id}/records",
        {
            "actor_user_id": pm_id,
            "record_type": "feature",
            "titulo": nombre,
            "descripcion": descripcion,
            "parent_id": sprint_id,
            "initial_state": estado_inicial,
            "data": {
                "tipo": "desarrollo",
                "prioridad": prioridad,
                "bloqueada": False,
                "story_points": story_points,
            },
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
        },
    )


def create_tarea(
    token: str,
    project_id: str,
    feature_id: str,
    actor_id: str,
    *,
    titulo: str,
    estado: str,
    asignado_ids: list[str] | None = None,
) -> dict:
    body: dict = {
        "actor_user_id": actor_id,
        "record_type": "task",
        "titulo": titulo,
        "parent_id": feature_id,
        "initial_state": estado,
    }
    if asignado_ids:
        body["assignee_ids"] = asignado_ids
    return post(token, f"/projects/{project_id}/records", body)


def transition(
    token: str,
    project_id: str,
    record_id: str,
    *,
    actor_user_id: str,
    action_id: str,
    target_state: str | None = None,
    ignore_errors: bool = False,
) -> dict | None:
    body: dict = {"actor_user_id": actor_user_id, "action_id": action_id}
    if target_state is not None:
        body["target_state"] = target_state
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


def create_hub_note(
    token: str, project_id: str, author_id: str, *, titulo: str, contenido: str
) -> dict:
    return post(
        token,
        f"/projects/{project_id}/hub-entries",
        {
            "author_id": author_id,
            "tipo": "note",
            "titulo": titulo,
            "contenido": contenido,
            "visibilidad": "interno",
        },
    )


def create_hub_update(
    token: str, project_id: str, author_id: str, *, contenido: str
) -> dict:
    return post(
        token,
        f"/projects/{project_id}/hub-entries",
        {
            "author_id": author_id,
            "tipo": "update",
            "contenido": contenido,
            "visibilidad": "publico",
        },
    )


# ── Seed principal ────────────────────────────────────────────────────────────

def seed_scrum_demo() -> None:
    today = date.today()

    print("[scrum] Autenticando como PM demo...")
    auth = login("pm@center.demo")
    token = auth["access_token"]
    users = get_users()

    pm = users["pm@center.demo"]
    tech = users["dev@center.demo"]   # Tech Lead en este proyecto
    dev = users["dev2@center.demo"]   # Dev
    qa = users["qa@center.demo"]

    print("[scrum] Obteniendo organización...")
    _, orgs = http("GET", "/organizations", token=token)
    org_id = orgs[0]["id"]

    # ── Proyecto ──────────────────────────────────────────────────────────────
    print("[scrum] Creando proyecto Scrum...")
    proyecto = post(
        token,
        "/projects",
        {
            "organization_id": org_id,
            "created_by": pm["id"],
            "nombre": "App Mobile — Scrum Demo",
            "descripcion": "Proyecto Scrum interno: Product Backlog, sprints, historias y tareas técnicas.",
            "pack_slug": "software",
            "template_slug": "t6_scrum_interno",
            "fecha_inicio": add_days(today, -42),
            "fecha_fin": add_days(today, 90),
        },
    )
    pid = proyecto["id"]
    print(f"[scrum] Proyecto creado: {pid}")

    for user_id, rol in [
        (pm["id"],   "pm"),
        (tech["id"], "tech_lead"),
        (dev["id"],  "dev"),
        (qa["id"],   "qa"),
    ]:
        add_member(token, pid, pm["id"], user_id, rol)

    # ── Sprint 0 (completado) ─────────────────────────────────────────────────
    print("[scrum] Creando Sprint 0 (completado)...")
    sprint0 = create_sprint(
        token, pid, pm["id"],
        nombre="Sprint 0 — Setup y autenticación",
        orden=1,
        fecha_inicio=add_days(today, -42),
        fecha_fin=add_days(today, -29),
        sprint_goal="Infraestructura base, CI/CD y flujo de autenticación completo.",
        velocidad_planeada=34,
    )
    sprint0_historias = [
        ("Configurar repositorio y CI/CD",        "8",  "alta"),
        ("Login con email y contraseña",           "5",  "alta"),
        ("Registro de usuario con validación",     "5",  "alta"),
        ("Recuperación de contraseña por email",   "3",  "media"),
    ]
    for nombre, sp, prio in sprint0_historias:
        h = create_historia(
            token, pid, pm["id"],
            nombre=nombre,
            sprint_id=sprint0["id"],
            story_points=sp,
            prioridad=prio,
            estado_inicial="product_backlog",
            fecha_inicio=add_days(today, -42),
            fecha_fin=add_days(today, -29),
        )
        transition(token, pid, h["id"], actor_user_id=pm["id"], action_id="comprometer_sprint", ignore_errors=True)
        transition(token, pid, h["id"], actor_user_id=tech["id"], action_id="pasar_a_uat", ignore_errors=True)
        transition(token, pid, h["id"], actor_user_id=qa["id"], action_id="enviar_al_pm", ignore_errors=True)
        transition(token, pid, h["id"], actor_user_id=pm["id"], action_id="completar", ignore_errors=True)
        create_tarea(token, pid, h["id"], tech["id"], titulo=f"Impl. {nombre}", estado="completed", asignado_ids=[tech["id"]])
    transition(token, pid, sprint0["id"], actor_user_id=pm["id"], action_id="sync", target_state="completado", ignore_errors=True)

    # ── Sprint 1 (en progreso) ────────────────────────────────────────────────
    print("[scrum] Creando Sprint 1 (en progreso)...")
    sprint1 = create_sprint(
        token, pid, pm["id"],
        nombre="Sprint 1 — Perfil y onboarding",
        orden=2,
        fecha_inicio=add_days(today, -14),
        fecha_fin=add_days(today, 0),
        sprint_goal="Pantallas de perfil, onboarding de usuario nuevo y avatar con crop.",
        velocidad_planeada=31,
    )
    transition(token, pid, sprint1["id"], actor_user_id=pm["id"], action_id="sync", target_state="en_progreso", ignore_errors=True)

    sprint1_spec = [
        ("Pantalla de perfil de usuario",    "5",  "alta",   "uat"),
        ("Flujo onboarding nuevo usuario",   "8",  "alta",   "en_progreso"),
        ("Upload y crop de avatar",          "5",  "media",  "en_progreso"),
        ("Notificaciones push — permisos",   "3",  "media",  "esperando_liberacion_pm"),
    ]
    sprint1_historias: list[dict] = []
    for nombre, sp, prio, estado_target in sprint1_spec:
        h = create_historia(
            token, pid, pm["id"],
            nombre=nombre,
            sprint_id=sprint1["id"],
            story_points=sp,
            prioridad=prio,
            estado_inicial="product_backlog",
            fecha_inicio=add_days(today, -14),
            fecha_fin=add_days(today, 0),
        )
        transition(token, pid, h["id"], actor_user_id=pm["id"], action_id="comprometer_sprint", ignore_errors=True)
        if estado_target in ("en_progreso", "uat", "esperando_liberacion_pm"):
            pass  # ya en pendiente, las pasan los devs
        if estado_target in ("uat", "esperando_liberacion_pm"):
            transition(token, pid, h["id"], actor_user_id=tech["id"], action_id="pasar_a_uat", ignore_errors=True)
        if estado_target == "esperando_liberacion_pm":
            transition(token, pid, h["id"], actor_user_id=qa["id"], action_id="enviar_al_pm", ignore_errors=True)
        sprint1_historias.append(h)

    for i, h in enumerate(sprint1_historias):
        task_states = ["in_progress", "ready_for_test", "completed", "to_do"]
        for j in range(3):
            create_tarea(
                token, pid, h["id"], tech["id"],
                titulo=f"Subtarea {j + 1} — {h['titulo'][:30]}",
                estado=task_states[(i + j) % len(task_states)],
                asignado_ids=[dev["id"] if j % 2 == 0 else tech["id"]],
            )

    # ── Sprint 2 (pendiente) ──────────────────────────────────────────────────
    print("[scrum] Creando Sprint 2 (pendiente)...")
    sprint2 = create_sprint(
        token, pid, pm["id"],
        nombre="Sprint 2 — Dashboard y analíticas",
        orden=3,
        fecha_inicio=add_days(today, 1),
        fecha_fin=add_days(today, 14),
        sprint_goal="Dashboard con métricas clave, gráficos de actividad y filtros por período.",
        velocidad_planeada=28,
    )
    sprint2_spec = [
        ("Dashboard con métricas clave",     "8",  "alta"),
        ("Gráficos de actividad semanal",    "5",  "media"),
        ("Filtros por período y exportación","3",  "media"),
    ]
    for nombre, sp, prio in sprint2_spec:
        h = create_historia(
            token, pid, pm["id"],
            nombre=nombre,
            sprint_id=sprint2["id"],
            story_points=sp,
            prioridad=prio,
            estado_inicial="product_backlog",
            fecha_inicio=add_days(today, 1),
            fecha_fin=add_days(today, 14),
        )
        transition(token, pid, h["id"], actor_user_id=pm["id"], action_id="comprometer_sprint", ignore_errors=True)

    # ── Product Backlog (sin sprint) ──────────────────────────────────────────
    print("[scrum] Poblando Product Backlog...")
    backlog_spec = [
        ("Modo oscuro — theming global",          "?",  "baja"),
        ("Integración con Google Calendar",        "13", "media"),
        ("Búsqueda global en la app",              "8",  "alta"),
        ("Historial de actividad del usuario",     "5",  "media"),
        ("Soporte offline básico (PWA)",            "13", "baja"),
    ]
    for nombre, sp, prio in backlog_spec:
        create_historia(
            token, pid, pm["id"],
            nombre=nombre,
            sprint_id=None,
            story_points=sp,
            prioridad=prio,
            estado_inicial="product_backlog",
            fecha_inicio=add_days(today, 14),
            fecha_fin=add_days(today, 60),
        )

    # ── Hub entries ───────────────────────────────────────────────────────────
    print("[scrum] Agregando entradas al hub...")
    create_hub_update(
        token, pid, pm["id"],
        contenido="Sprint 0 cerrado con 21 SP entregados de 34 planeados. Login y CI/CD completos.",
    )
    create_hub_note(
        token, pid, pm["id"],
        titulo="Retrospectiva Sprint 0",
        contenido=(
            "**Qué salió bien:** CI/CD funcionando desde el día 1. "
            "Equipo coordinado en code review.\n\n"
            "**Qué mejorar:** Estimaciones de las tareas de setup fueron optimistas. "
            "El avatar quedó fuera del sprint.\n\n"
            "**Acción:** Spike de 1 SP para evaluar librerías de crop antes de Sprint 1."
        ),
    )
    create_hub_note(
        token, pid, pm["id"],
        titulo=f"Sprint Goal — Sprint 1",
        contenido=(
            "**Objetivo:** Pantallas de perfil, onboarding de usuario nuevo y avatar con crop.\n\n"
            "**Velocidad planeada:** 31 SP\n"
            "**Equipo:** PM, Tech Lead, Dev, QA\n\n"
            "Definición de Done: historia integrada en staging, pasó smoke tests y QA aprobó."
        ),
    )
    create_hub_update(
        token, pid, tech["id"],
        contenido="Pantalla de perfil en UAT. Pendiente feedback QA antes de cerrar.",
    )
    create_hub_update(
        token, pid, dev["id"],
        contenido="Onboarding: animaciones de steps listas. Falta integración con backend de analytics.",
    )

    print(f"\n[scrum] OK — Proyecto: 'App Mobile - Scrum Demo' (id: {pid})")
    print("[scrum] Abrilo en http://localhost:5173 y navega a Alcance para ver los sprints.")


if __name__ == "__main__":
    seed_scrum_demo()
