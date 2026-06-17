"""
Crea un proyecto Scrum interno (t6) con datos abundantes en 4 sprints.

Preferir: scripts/seed_scrum_pack.py

  Logistics Hub — inventario, rutas, tracking y analíticas.

Uso (API en :8000, usuarios demo existentes):
  .venv\\Scripts\\python.exe scripts/seed_scrum_rich.py

Requisitos previos:
  python scripts/reset_and_seed_demo.py --seed-only

No borra la BD (proyecto aditivo).
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

# (titulo, story_points, prioridad, estado_final, [horas_tareas...])
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


# ── HTTP ──────────────────────────────────────────────────────────────────────


def http(method, path, *, body=None, token=None, expect_status=None):
    url = f"{BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            raw = res.read().decode()
            parsed = json.loads(raw) if raw else None
            if expect_status and res.status != expect_status:
                raise RuntimeError(f"expected {expect_status}, got {res.status}: {raw[:300]}")
            return res.status, parsed
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        if expect_status and e.code == expect_status:
            return e.code, parsed
        raise RuntimeError(f"HTTP {e.code}: {raw[:400]}") from e


def post(token, path, body, *, expect=201):
    _, data = http("POST", path, body=body, token=token, expect_status=expect)
    return data


def patch(token, path, body):
    _, data = http("PATCH", path, body=body, token=token, expect_status=200)
    return data


def login(email):
    _, auth = http("POST", "/auth/login", body={"email": email, "password": DEMO_PASSWORD}, expect_status=200)
    return auth


def get_users():
    _, users = http("GET", "/users")
    return {u["email"]: u for u in users}


def add_days(base: date, days: int) -> str:
    return (base + timedelta(days=days)).isoformat()


# ── Helpers ───────────────────────────────────────────────────────────────────


def add_member(token, pid, pm_id, user_id, rol):
    try:
        post(token, f"/projects/{pid}/members", {"actor_user_id": pm_id, "user_id": user_id, "rol": rol})
    except RuntimeError:
        pass


def mk_sprint(token, pid, pm_id, *, nombre, orden, fi, ff, goal, horas_planeadas):
    return post(token, f"/projects/{pid}/records", {
        "actor_user_id": pm_id,
        "record_type": "milestone",
        "titulo": nombre,
        "descripcion": goal,
        "data": {
            "tipo": "sprint",
            "sprint_goal": goal,
            "horas_planeadas": horas_planeadas,
        },
        "orden": orden,
        "fecha_inicio": fi,
        "fecha_fin": ff,
    })


def mk_epic(token, pid, pm_id, *, nombre):
    return post(token, f"/projects/{pid}/records", {
        "actor_user_id": pm_id,
        "record_type": "task",
        "titulo": nombre,
        "data": {"scrum_role": "epic"},
    })


def mk_historia(token, pid, pm_id, *, nombre, epic_id, prio, desc=""):
    return post(token, f"/projects/{pid}/records", {
        "actor_user_id": pm_id,
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


def mk_backlog(token, pid, pm_id, *, nombre, epic_id, prio, desc=""):
    return mk_historia(
        token, pid, pm_id,
        nombre=nombre,
        epic_id=epic_id,
        prio=prio,
        desc=desc,
    )


def mk_tarea(token, pid, story_id, actor_id, *, titulo, estado, asignee=None, horas=None):
    body = {
        "actor_user_id": actor_id,
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


def mk_subtarea(token, pid, parent_dev_id, actor_id, *, titulo, estado, asignee=None, horas=None):
    body = {
        "actor_user_id": actor_id,
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


def seed_subtareas(token, pid, parent_dev_id, actor_id, *, asignee=None, count: int = 2):
    estados = ["to_do", "in_progress", "completed"]
    for i in range(count):
        mk_subtarea(
            token, pid, parent_dev_id, actor_id,
            titulo=f"Subtarea {i + 1}",
            estado=estados[i % len(estados)],
            asignee=asignee,
            horas=1.5 + i,
        )


def seed_tareas(
    token,
    pid,
    feature_id,
    actor_id,
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
            token, pid, feature_id, actor_id,
            titulo=titulo,
            estado=estado,
            asignee=asignee,
            horas=horas,
        )
        if i == 0 and len(horas_list) >= 2:
            seed_subtareas(token, pid, task["id"], actor_id, asignee=asignee, count=2)


def tr(token, pid, rid, *, actor, action, target=None, side_effect_context=None, silent=True):
    body = {"actor_user_id": actor, "action_id": action}
    if target:
        body["target_state"] = target
    if side_effect_context:
        body["side_effect_context"] = side_effect_context
    try:
        _, d = http("POST", f"/projects/{pid}/records/{rid}/transition", body=body, token=token, expect_status=200)
        return d
    except RuntimeError:
        if silent:
            return None
        raise


def task_estado_for_final(estado_final: str) -> str | None:
    """Estados de tarea que permiten pasar_a_uat (gate uat_tasks_complete)."""
    if estado_final in ("completado", "uat", "esperando_liberacion_pm", "esperando_validacion_cliente"):
        return "ready_for_test"
    if estado_final == "pendiente":
        return "to_do"
    return None  # en_progreso: mezcla to_do / in_progress / …


def advance_historia(
    token,
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
    tr(
        token, pid, feature_id, actor=pm_id, action="comprometer_sprint",
        side_effect_context={"sprint_id": sprint_id},
    )
    if horas_list:
        seed_tareas(
            token, pid, feature_id, tech_id, horas_list,
            asignee=assignee,
            task_estado=task_estado or task_estado_for_final(estado_final),
        )
    if estado_final == "completado":
        tr(token, pid, feature_id, actor=tech_id, action="pasar_a_uat")
        tr(token, pid, feature_id, actor=qa_id, action="enviar_al_pm")
        tr(token, pid, feature_id, actor=pm_id, action="completar")
    elif estado_final in ("uat", "esperando_liberacion_pm"):
        tr(token, pid, feature_id, actor=tech_id, action="pasar_a_uat")
        if estado_final == "esperando_liberacion_pm":
            tr(token, pid, feature_id, actor=qa_id, action="enviar_al_pm")
    # pendiente / en_progreso: sync de tareas deja el estado coherente


def hub_note(token, pid, author, *, titulo, contenido):
    return post(token, f"/projects/{pid}/hub-entries", {
        "author_id": author, "tipo": "note", "titulo": titulo,
        "contenido": contenido, "visibilidad": "interno",
    })


def hub_update(token, pid, author, *, contenido):
    return post(token, f"/projects/{pid}/hub-entries", {
        "author_id": author, "tipo": "update",
        "contenido": contenido, "visibilidad": "publico",
    })


# ── Seed principal ────────────────────────────────────────────────────────────


def seed_logistics_hub(token, users, org_id, today: date) -> dict[str, int | str]:
    pm = users["pm@center.demo"]
    tech = users["dev@center.demo"]
    dev = users["dev2@center.demo"]
    qa = users["qa@center.demo"]
    pm_id = pm["id"]

    print("  Creando Logistics Hub (t6_scrum_interno)...")
    p = post(token, "/projects", {
        "organization_id": org_id,
        "created_by": pm_id,
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
        add_member(token, pid, pm_id, uid, rol)

    assignees = [tech["id"], dev["id"]]
    historia_count = 0
    task_count = 0

    epics = {
        "inventario": mk_epic(token, pid, pm_id, nombre="Inventario")["id"],
        "operaciones": mk_epic(token, pid, pm_id, nombre="Operaciones")["id"],
        "tracking": mk_epic(token, pid, pm_id, nombre="Tracking")["id"],
        "analytics": mk_epic(token, pid, pm_id, nombre="Analytics")["id"],
        "plataforma": mk_epic(token, pid, pm_id, nombre="Plataforma")["id"],
    }
    epic_by_sprint = {
        1: epics["inventario"],
        2: epics["operaciones"],
        3: epics["tracking"],
        4: epics["analytics"],
    }

    for nombre, orden, start_off, end_off, goal, sprint_state, horas_plan in SPRINTS:
        sprint = mk_sprint(
            token, pid, pm_id,
            nombre=nombre,
            orden=orden,
            fi=add_days(today, start_off),
            ff=add_days(today, end_off),
            goal=goal,
            horas_planeadas=horas_plan,
        )
        if sprint_state == "en_progreso":
            tr(token, pid, sprint["id"], actor=pm_id, action="sync", target="en_progreso")

        specs = SPRINT_HISTORIAS[orden]
        epic_id = epic_by_sprint.get(orden, epics["plataforma"])
        for idx, (titulo, _sp, prio, estado_final, horas_list) in enumerate(specs):
            h = mk_historia(
                token, pid, pm_id,
                nombre=titulo,
                epic_id=epic_id,
                prio=prio,
            )
            historia_count += 1
            assignee = assignees[idx % len(assignees)]
            if horas_list:
                task_count += len(horas_list)

            advance_historia(
                token, pid, pm_id, tech["id"], qa["id"], h["id"], sprint["id"], estado_final,
                horas_list=horas_list,
                assignee=assignee,
            )

        if sprint_state == "completado":
            tr(token, pid, sprint["id"], actor=pm_id, action="sync", target="completado")

    backlog_count = 0
    backlog_epics = [epics["plataforma"], epics["tracking"], epics["analytics"], epics["operaciones"]]
    for idx, (titulo, _sp, prio, horas_list) in enumerate(BACKLOG):
        epic_id = backlog_epics[idx % len(backlog_epics)]
        h = mk_backlog(token, pid, pm_id, nombre=titulo, epic_id=epic_id, prio=prio)
        backlog_count += 1
        if horas_list:
            seed_tareas(
                token, pid, h["id"], tech["id"], horas_list,
                asignee=assignees[idx % len(assignees)],
                task_estado="to_do",
            )
            task_count += len(horas_list)

    hub_update(token, pid, pm_id, contenido="Sprint 1 completado. Inventario base operativo en staging.")
    hub_note(token, pid, pm_id,
        titulo="Retro Sprint 1 — Fundamentos",
        contenido=(
            "**Bien:** Modelo de datos sólido; import CSV superó expectativas de volumen.\n\n"
            "**Mejorar:** Tests de integración tardaron; reservar buffer en Sprint 2.\n\n"
            "**Acción:** Documentar convenciones de SKU antes del grooming de operaciones."
        ),
    )
    hub_note(token, pid, pm_id,
        titulo="Sprint 2 — Definition of Done",
        contenido=(
            "Historia Done cuando:\n"
            "- Código mergeado y revisado\n"
            "- Movimientos auditables con trazabilidad\n"
            "- QA en staging sin blockers\n"
            "- Alertas de mínimos validadas con datos reales"
        ),
    )
    hub_update(token, pid, tech["id"],
        contenido="Recepción de mercadería en UAT. Movimientos entre almacenes ~70% front.")
    hub_update(token, pid, dev["id"],
        contenido="Grooming Sprint 3: estimación tracking y webhooks TMS el jueves.")
    hub_note(token, pid, pm_id,
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


def main():
    today = date.today()

    print("[seed-scrum-rich] Autenticando...")
    auth = login("pm@center.demo")
    token = auth["access_token"]
    users = get_users()

    required = ["pm@center.demo", "dev@center.demo", "dev2@center.demo", "qa@center.demo"]
    missing = [e for e in required if e not in users]
    if missing:
        print(f"[ERROR] Usuarios faltantes: {missing}")
        print("Ejecuta primero: python scripts/reset_and_seed_demo.py --seed-only")
        sys.exit(1)

    _, orgs = http("GET", "/organizations", token=token)
    org_id = orgs[0]["id"]

    print("\n[seed-scrum-rich] Sembrando Logistics Hub...")
    stats = seed_logistics_hub(token, users, org_id, today)

    pid = stats["project_id"]
    print("\n[seed-scrum-rich] Listo.")
    print(f"  Proyecto:     http://localhost:5173/projects/{pid}")
    print(f"  Sprints:      {stats['sprints']}")
    print(f"  Historias:    {stats['historias_sprint']} (en sprints) + {stats['backlog']} (backlog)")
    print(f"  Tareas:       {stats['tasks']}")
    print("\n  Vistas: Product Backlog · Sprint Planning · Sprint Board · Burndown")


if __name__ == "__main__":
    main()
