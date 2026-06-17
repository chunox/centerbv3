"""
Crea 2 proyectos Scrum demo listos para ver en la app:

  1. CRM Platform          (t6_scrum_interno)  — equipo interno, sin cliente
  2. E-commerce Relaunch   (t7_scrum_cliente)   — con validacion del cliente

Uso:
  .venv\\Scripts\\python.exe scripts/seed_scrum_duo.py

Requiere API corriendo en :8000 y usuarios demo (reset_and_seed_demo.py).
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


def add_days(base, days):
    return (base + timedelta(days=days)).isoformat()


# ── Helpers reutilizables ─────────────────────────────────────────────────────

def add_member(token, pid, pm_id, user_id, rol):
    try:
        post(token, f"/projects/{pid}/members", {"actor_user_id": pm_id, "user_id": user_id, "rol": rol})
    except RuntimeError:
        pass


def mk_sprint(token, pid, pm_id, *, nombre, orden, fi, ff, goal):
    return post(token, f"/projects/{pid}/records", {
        "actor_user_id": pm_id,
        "record_type": "milestone",
        "titulo": nombre,
        "descripcion": goal,
        "data": {"tipo": "entrega", "sprint_goal": goal},
        "orden": orden,
        "fecha_inicio": fi,
        "fecha_fin": ff,
    })


def mk_historia(token, pid, pm_id, *, nombre, sprint_id, prio, desc=""):
    return post(token, f"/projects/{pid}/records", {
        "actor_user_id": pm_id,
        "record_type": "feature",
        "titulo": nombre,
        "descripcion": desc,
        "parent_id": sprint_id,
        "initial_state": "product_backlog",
        "data": {"tipo": "desarrollo", "prioridad": prio, "bloqueada": False},
    })


def mk_backlog(token, pid, pm_id, *, nombre, prio, desc=""):
    return mk_historia(token, pid, pm_id, nombre=nombre, sprint_id=None, prio=prio, desc=desc)


def mk_tarea(token, pid, feature_id, actor_id, *, titulo, estado, asignee=None, horas=None):
    body = {
        "actor_user_id": actor_id,
        "record_type": "task",
        "titulo": titulo,
        "parent_id": feature_id,
        "initial_state": estado,
    }
    if horas is not None:
        body["data"] = {"estimacion_horas": horas}
    if asignee:
        body["assignee_ids"] = [asignee]
    return post(token, f"/projects/{pid}/records", body)


def seed_tareas(token, pid, feature_id, actor_id, horas_list, *, asignee=None, estado=None):
    estados = ["to_do", "in_progress", "completed", "ready_for_test"]
    for i, horas in enumerate(horas_list):
        mk_tarea(
            token, pid, feature_id, actor_id,
            titulo=f"Tarea {i + 1}",
            estado=estado or estados[i % len(estados)],
            asignee=asignee,
            horas=horas,
        )


def tr(token, pid, rid, *, actor, action, target=None, silent=True):
    body = {"actor_user_id": actor, "action_id": action}
    if target:
        body["target_state"] = target
    try:
        _, d = http("POST", f"/projects/{pid}/records/{rid}/transition", body=body, token=token, expect_status=200)
        return d
    except RuntimeError:
        if silent:
            return None
        raise


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


# ── Proyecto 1: CRM Platform (t6_scrum_interno) ───────────────────────────────

def seed_crm(token, users, org_id, today):
    pm    = users["pm@center.demo"]
    tech  = users["dev@center.demo"]
    dev   = users["dev2@center.demo"]
    qa    = users["qa@center.demo"]
    pm_id = pm["id"]

    print("  Creando proyecto CRM Platform (t6_scrum_interno)...")
    p = post(token, "/projects", {
        "organization_id": org_id,
        "created_by": pm_id,
        "nombre": "CRM Platform",
        "descripcion": "Sistema CRM interno. Gestion de contactos, pipeline de ventas y reportes.",
        "pack_slug": "software",
        "template_slug": "t6_scrum_interno",
        "fecha_inicio": add_days(today, -56),
        "fecha_fin": add_days(today, 84),
    })
    pid = p["id"]

    for uid, rol in [(pm_id, "pm"), (tech["id"], "tech_lead"), (dev["id"], "dev"), (qa["id"], "qa")]:
        add_member(token, pid, pm_id, uid, rol)

    # Sprint 1 — completado
    s1 = mk_sprint(token, pid, pm_id,
        nombre="Sprint 1 — Base y contactos",
        orden=1,
        fi=add_days(today, -56),
        ff=add_days(today, -43),
        goal="Modelo de datos, API REST, y CRUD completo de contactos.",
    )
    s1_spec = [
        ("Modelo de datos + migraciones Alembic",   "alta",   [4, 4]),
        ("API REST: CRUD de contactos",              "alta",   [4, 4]),
        ("UI: lista de contactos con filtros",       "alta",   [3, 2]),
        ("UI: formulario de contacto con validacion","media",  [3, 2]),
        ("Tests unitarios capa de servicio",         "media",  [2, 1]),
    ]
    for nombre, prio, horas_list in s1_spec:
        h = mk_historia(token, pid, pm_id, nombre=nombre, sprint_id=s1["id"], prio=prio)
        patch(token, f"/projects/{pid}/records/{h['id']}", {"actor_user_id": pm_id, "parent_id": s1["id"]})
        tr(token, pid, h["id"], actor=pm_id, action="comprometer_sprint")
        seed_tareas(token, pid, h["id"], tech["id"], horas_list, asignee=tech["id"], estado="completed")
        tr(token, pid, h["id"], actor=tech["id"], action="pasar_a_uat")
        tr(token, pid, h["id"], actor=qa["id"], action="enviar_al_pm")
        tr(token, pid, h["id"], actor=pm_id, action="completar")
    tr(token, pid, s1["id"], actor=pm_id, action="sync", target="completado")

    # Sprint 2 — en progreso
    s2 = mk_sprint(token, pid, pm_id,
        nombre="Sprint 2 — Pipeline de ventas",
        orden=2,
        fi=add_days(today, -14),
        ff=add_days(today, -1),
        goal="Kanban de oportunidades con etapas configurables y valor estimado por deal.",
    )
    tr(token, pid, s2["id"], actor=pm_id, action="sync", target="en_progreso")

    s2_spec = [
        ("Modelo de oportunidades y pipeline",    "alta",   "uat",              [4, 4]),
        ("Kanban de deals con drag & drop",       "alta",   "en_progreso",      [4, 4]),
        ("Valor estimado y probabilidad por etapa","media",  "en_progreso",      [2.5, 2.5]),
        ("Vista de oportunidades ganadas/perdidas","media",  "pendiente",       [1.5, 1.5]),
    ]
    for nombre, prio, estado_final, horas_list in s2_spec:
        h = mk_historia(token, pid, pm_id, nombre=nombre, sprint_id=s2["id"], prio=prio)
        patch(token, f"/projects/{pid}/records/{h['id']}", {"actor_user_id": pm_id, "parent_id": s2["id"]})
        tr(token, pid, h["id"], actor=pm_id, action="comprometer_sprint")
        seed_tareas(token, pid, h["id"], tech["id"], horas_list, asignee=dev["id"])
        if estado_final in ("uat", "esperando_liberacion_pm"):
            tr(token, pid, h["id"], actor=tech["id"], action="pasar_a_uat")
        if estado_final == "esperando_liberacion_pm":
            tr(token, pid, h["id"], actor=qa["id"], action="enviar_al_pm")

    # Sprint 3 — pendiente (planning)
    s3 = mk_sprint(token, pid, pm_id,
        nombre="Sprint 3 — Reportes y analíticas",
        orden=3,
        fi=add_days(today, 0),
        ff=add_days(today, 13),
        goal="Dashboard de rendimiento de ventas con gráficos y exportacion CSV.",
    )
    s3_spec = [
        ("Dashboard con metricas clave de ventas", "alta",   [4, 4]),
        ("Graficos de conversion por etapa",       "media",  [2.5, 2.5]),
        ("Exportacion CSV de contactos y deals",   "media",  [1.5, 1.5]),
    ]
    for nombre, prio, horas_list in s3_spec:
        h = mk_historia(token, pid, pm_id, nombre=nombre, sprint_id=s3["id"], prio=prio)
        patch(token, f"/projects/{pid}/records/{h['id']}", {"actor_user_id": pm_id, "parent_id": s3["id"]})
        tr(token, pid, h["id"], actor=pm_id, action="comprometer_sprint")
        seed_tareas(token, pid, h["id"], tech["id"], horas_list, asignee=dev["id"])

    # Product Backlog
    backlog_crm = [
        ("Integracion con Gmail/Outlook",          "alta",   [6, 4]),
        ("App movil: vista de contactos",          "media",  [8]),
        ("Automatizacion: recordatorios de deals", "media",  [4, 4]),
        ("Roles y permisos granulares",            "alta",   [3, 2]),
        ("Historial de interacciones por contacto","media",  [2.5, 2.5]),
        ("Busqueda avanzada full-text",            "baja",   [4, 4]),
        ("Notificaciones en tiempo real (WS)",     "baja",   None),
    ]
    for nombre, prio, horas_list in backlog_crm:
        h = mk_backlog(token, pid, pm_id, nombre=nombre, prio=prio)
        if horas_list:
            seed_tareas(token, pid, h["id"], tech["id"], horas_list, asignee=dev["id"])

    # Hub
    hub_update(token, pid, pm_id, contenido="Sprint 1 completado. CRUD de contactos en produccion.")
    hub_note(token, pid, pm_id,
        titulo="Retro Sprint 1",
        contenido=(
            "**Bien:** Modelo de datos solido, cero regresiones.\n\n"
            "**Mejorar:** Los tests tardaron mas de lo esperado. Reservar 1 dia para testing.\n\n"
            "**Accion:** Agregar linting CI en PR para reducir feedback loops."
        ),
    )
    hub_note(token, pid, pm_id,
        titulo="Sprint 2 — Definition of Done",
        contenido=(
            "Una historia se considera Done cuando:\n"
            "- Codigo revisado y mergeado a main\n"
            "- Tests automaticos pasando\n"
            "- QA aprobado en staging\n"
            "- Sin issues abiertos relacionados"
        ),
    )
    hub_update(token, pid, tech["id"], contenido="Kanban de deals: back-end listo, front en progreso. ETA: 2 dias.")
    hub_update(token, pid, dev["id"], contenido="Inicio de Sprint 3 planning. Estimar tareas en grooming.")

    print(f"  [OK] CRM Platform — id: {pid}")
    return pid


# ── Proyecto 2: E-commerce Relaunch (t7_scrum_cliente) ────────────────────────

def seed_ecommerce(token_pm, token_cliente, users, org_id, today):
    pm      = users["pm@center.demo"]
    tech    = users["dev@center.demo"]
    dev     = users["dev2@center.demo"]
    qa      = users["qa@center.demo"]
    cliente = users["cliente@center.demo"]
    pm_id   = pm["id"]

    print("  Creando proyecto E-commerce Relaunch (t7_scrum_cliente)...")
    p = post(token_pm, "/projects", {
        "organization_id": org_id,
        "created_by": pm_id,
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
        add_member(token_pm, pid, pm_id, uid, rol)

    # Sprint 1 — completado (con validacion de cliente)
    s1 = mk_sprint(token_pm, pid, pm_id,
        nombre="Sprint 1 — Catalogo de productos",
        orden=1,
        fi=add_days(today, -42),
        ff=add_days(today, -29),
        goal="Catalogo publico con filtros, busqueda y detalle de producto.",
    )
    s1_spec = [
        ("Pagina de catalogo con grilla de productos", "alta",   [4, 4]),
        ("Filtros por categoria, precio y disponibilidad","alta", [2.5, 2.5]),
        ("Pagina de detalle de producto con galeria",  "alta",   [4, 4]),
        ("Busqueda por nombre y descripcion",          "media",  [2.5, 2.5]),
    ]
    for nombre, prio, horas_list in s1_spec:
        h = mk_historia(token_pm, pid, pm_id, nombre=nombre, sprint_id=s1["id"], prio=prio)
        patch(token_pm, f"/projects/{pid}/records/{h['id']}", {"actor_user_id": pm_id, "parent_id": s1["id"]})
        tr(token_pm, pid, h["id"], actor=pm_id, action="comprometer_sprint")
        seed_tareas(token_pm, pid, h["id"], tech["id"], horas_list, asignee=tech["id"], estado="completed")
        tr(token_pm, pid, h["id"], actor=tech["id"], action="pasar_a_uat")
        tr(token_pm, pid, h["id"], actor=qa["id"], action="enviar_al_pm")
        tr(token_pm, pid, h["id"], actor=pm_id, action="liberar_cliente")
        tr(token_cliente, pid, h["id"], actor=cliente["id"], action="confirmar")
    tr(token_pm, pid, s1["id"], actor=pm_id, action="sync", target="completado")

    # Sprint 2 — en progreso (con historias en distintos estados del flujo con cliente)
    s2 = mk_sprint(token_pm, pid, pm_id,
        nombre="Sprint 2 — Carrito y checkout",
        orden=2,
        fi=add_days(today, -14),
        ff=add_days(today, -1),
        goal="Flujo completo de compra: agregar al carrito, checkout, pago y confirmacion de pedido.",
    )
    tr(token_pm, pid, s2["id"], actor=pm_id, action="sync", target="en_progreso")

    s2_spec = [
        ("Carrito persistente (localStorage + API)",     "alta",   "esperando_validacion_cliente", [2.5, 2.5]),
        ("Checkout: datos de envio y resumen",           "alta",   "esperando_liberacion_pm",     [4, 4]),
        ("Integracion con pasarela de pago (Stripe)",    "alta",   "uat",                          [4, 4]),
        ("Pagina de confirmacion y email transaccional", "media",  "en_progreso",                  [2.5, 2.5]),
        ("Validaciones de stock en checkout",            "media",  "pendiente",                    [1.5, 1.5]),
    ]
    for nombre, prio, estado_final, horas_list in s2_spec:
        h = mk_historia(token_pm, pid, pm_id, nombre=nombre, sprint_id=s2["id"], prio=prio)
        patch(token_pm, f"/projects/{pid}/records/{h['id']}", {"actor_user_id": pm_id, "parent_id": s2["id"]})
        tr(token_pm, pid, h["id"], actor=pm_id, action="comprometer_sprint")
        seed_tareas(token_pm, pid, h["id"], tech["id"], horas_list, asignee=dev["id"])
        if estado_final in ("uat", "esperando_liberacion_pm", "esperando_validacion_cliente"):
            tr(token_pm, pid, h["id"], actor=tech["id"], action="pasar_a_uat")
        if estado_final in ("esperando_liberacion_pm", "esperando_validacion_cliente"):
            tr(token_pm, pid, h["id"], actor=qa["id"], action="enviar_al_pm")
        if estado_final == "esperando_validacion_cliente":
            tr(token_pm, pid, h["id"], actor=pm_id, action="liberar_cliente")

    s3 = mk_sprint(token_pm, pid, pm_id,
        nombre="Sprint 3 — Panel de cliente",
        orden=3,
        fi=add_days(today, 0),
        ff=add_days(today, 13),
        goal="Historial de pedidos, estado en tiempo real y gestion de direcciones del cliente.",
    )
    s3_spec = [
        ("Historial de pedidos con filtros",           "alta",   [4, 4]),
        ("Estado de pedido en tiempo real (polling)",  "alta",   [2.5, 2.5]),
        ("Gestion de direcciones de envio",            "media",  [2.5, 2.5]),
        ("Descarga de factura en PDF",                 "baja",   [1.5, 1.5]),
    ]
    for nombre, prio, horas_list in s3_spec:
        h = mk_historia(token_pm, pid, pm_id, nombre=nombre, sprint_id=s3["id"], prio=prio)
        patch(token_pm, f"/projects/{pid}/records/{h['id']}", {"actor_user_id": pm_id, "parent_id": s3["id"]})
        tr(token_pm, pid, h["id"], actor=pm_id, action="comprometer_sprint")
        seed_tareas(token_pm, pid, h["id"], tech["id"], horas_list, asignee=dev["id"])

    backlog_ec = [
        ("Panel de administracion de productos",       "alta",   [6, 4]),
        ("Wishlist / lista de deseos",                 "media",  [3, 2]),
        ("Reviews y valoraciones de productos",        "media",  [4, 4]),
        ("Programa de puntos y fidelizacion",          "baja",   [8]),
        ("Integracion con ERP de inventario",          "alta",   None),
        ("App movil con React Native",                 "baja",   None),
    ]
    for nombre, prio, horas_list in backlog_ec:
        h = mk_backlog(token_pm, pid, pm_id, nombre=nombre, prio=prio)
        if horas_list:
            seed_tareas(token_pm, pid, h["id"], tech["id"], horas_list, asignee=dev["id"])

    hub_update(token_pm, pid, pm_id,
        contenido="Sprint 1 cerrado. Catalogo live en staging, aprobado por cliente.")
    hub_note(token_pm, pid, pm_id,
        titulo="Feedback cliente — Sprint 1",
        contenido=(
            "El cliente solicita:\n"
            "- Filtro por marca en el catalogo (P2)\n"
            "- Galeria con zoom en detalle de producto (P1)\n\n"
            "El zoom se agrega como historia en el backlog. El filtro por marca en Sprint 2 si hay capacidad."
        ),
    )
    hub_note(token_pm, pid, pm_id,
        titulo="Sprint 2 — Riesgos",
        contenido=(
            "**Integracion Stripe:** Primera vez que el equipo trabaja con esta API. "
            "Tech Lead investigara docs 1 dia antes de estimar tareas.\n\n"
            "**Buffer de QA:** Checkout requiere pruebas E2E en distintos browsers. "
            "Reservar 2 dias extra para QA en la segunda semana del sprint."
        ),
    )
    hub_update(token_pm, pid, tech["id"],
        contenido="Carrito validado por cliente. Checkout en UAT, pendiente aprobacion del PM.")
    hub_update(token_pm, pid, pm_id,
        contenido="Feedback del cliente: Carrito funciona bien en desktop. Pendiente prueba en mobile.")

    print(f"  [OK] E-commerce Relaunch — id: {pid}")
    return pid


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today = date.today()

    print("[seed-scrum-duo] Autenticando usuarios...")
    auth_pm      = login("pm@center.demo")
    auth_cliente = login("cliente@center.demo")
    token_pm      = auth_pm["access_token"]
    token_cliente = auth_cliente["access_token"]

    users = get_users()
    required = ["pm@center.demo", "dev@center.demo", "dev2@center.demo", "qa@center.demo", "cliente@center.demo"]
    missing = [e for e in required if e not in users]
    if missing:
        print(f"[ERROR] Usuarios faltantes: {missing}")
        print("Ejecuta primero: python scripts/reset_and_seed_demo.py")
        sys.exit(1)

    _, orgs = http("GET", "/organizations", token=token_pm)
    org_id = orgs[0]["id"]

    print("\n[1/2] CRM Platform (Scrum interno)...")
    pid_crm = seed_crm(token_pm, users, org_id, today)

    print("\n[2/2] E-commerce Relaunch (Scrum con cliente)...")
    pid_ec  = seed_ecommerce(token_pm, token_cliente, users, org_id, today)

    print("\n[seed-scrum-duo] Listo.")
    print(f"  CRM Platform:        http://localhost:5173/projects/{pid_crm}")
    print(f"  E-commerce Relaunch: http://localhost:5173/projects/{pid_ec}")
    print("\n  Ambos proyectos tienen Sprint Board, Product Backlog y Sprint Planning en el sidebar.")


if __name__ == "__main__":
    main()
