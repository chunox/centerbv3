"""
Proyecto demo Marketing 360° — campaña con briefing, piezas en 7 estados y dependencias.

Uso (API en :8000):
  .venv\\Scripts\\python.exe scripts/seed_marketing360_demo.py

Integrado en reset_and_seed_demo.py como proyecto adicional.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.reset_and_seed_demo import (  # noqa: E402
    DEMO_PASSWORD,
    add_days,
    add_member,
    create_project,
    create_record,
    ensure_user,
    http,
    login,
    post,
    transition_record,
    wait_for_api,
)

PROJECT_NAME = "Lanzamiento Q3 · Brand Awareness"

M360_USERS = [
    ("copy@center.demo", "Tomás Copy"),
    ("design@center.demo", "Valentina Diseño"),
    ("social@center.demo", "Nico Social"),
]

MEMBER_ROLES = [
    ("copy@center.demo", "copy"),
    ("design@center.demo", "diseno"),
    ("social@center.demo", "social"),
    ("cliente@center.demo", "cliente"),
]

# (titulo, target_state, canal, formato, assignee_email, fecha_publicacion_offset_days | None)
PIEZAS: list[tuple[str, str, str, str, str | None, int | None]] = [
    ("Copy LinkedIn thought leadership", "backlog", "linkedin", "copy", "copy@center.demo", 45),
    ("Newsletter Q3 kickoff", "backlog", "newsletter", "copy", "copy@center.demo", 42),
    ("Blog SEO pillar page", "redaccion", "blog_seo", "copy", "copy@center.demo", 40),
    ("Posts orgánicos Instagram x6", "redaccion", "organic_social", "carrusel", "copy@center.demo", 38),
    ("Script video brand 30s", "diseno_edicion", "meta_ads", "video", "design@center.demo", 35),
    ("Banners display set A", "diseno_edicion", "meta_ads", "banner", "design@center.demo", 33),
    ("Banners display set B", "control_calidad", "google_ads", "banner", "design@center.demo", 32),
    ("Landing awareness", "control_calidad", "blog_seo", "landing", "design@center.demo", 30),
    ("Key visual aprobación", "esperando_aprobacion", "meta_ads", "banner", "design@center.demo", 28),
    ("Reels TikTok/Reels x4", "programado", "organic_social", "reel", "social@center.demo", 25),
    ("Newsletter nurture #2", "programado", "newsletter", "copy", "copy@center.demo", 22),
    ("Subir anuncios Meta", "backlog", "meta_ads", "copy", "social@center.demo", 20),
    ("Google Search RSA", "publicado", "google_ads", "copy", "copy@center.demo", 18),
    ("Post lanzamiento LinkedIn", "publicado", "linkedin", "copy", "social@center.demo", 15),
]

STATE_CHAIN = [
    "iniciar_redaccion",
    "enviar_diseno",
    "enviar_qc",
    "solicitar_aprobacion",
    "aprobar",
    "publicar",
]

TARGET_INDEX = {
    "backlog": 0,
    "redaccion": 1,
    "diseno_edicion": 2,
    "control_calidad": 3,
    "esperando_aprobacion": 4,
    "programado": 5,
    "publicado": 6,
}


def create_dependency(token: str, project_id: str, pm_id: str, pred_id: str, succ_id: str) -> None:
    post(
        token,
        f"/projects/{project_id}/record-dependencies",
        {
            "actor_user_id": pm_id,
            "predecessor_id": pred_id,
            "successor_id": succ_id,
        },
    )


def advance_pieza(
    token: str,
    project_id: str,
    record_id: str,
    pm_id: str,
    cliente_id: str,
    target_state: str,
) -> None:
    steps = TARGET_INDEX.get(target_state, 0)
    for i in range(steps):
        action = STATE_CHAIN[i]
        actor = pm_id
        if action in ("aprobar", "rechazar"):
            cliente_token = login("cliente@center.demo")["access_token"]
            transition_record(
                cliente_token,
                project_id,
                record_id,
                actor_user_id=cliente_id,
                action_id=action,
                ignore_errors=True,
            )
            continue
        transition_record(
            token,
            project_id,
            record_id,
            actor_user_id=actor,
            action_id=action,
            ignore_errors=True,
        )


def seed_marketing360_project(
    token: str,
    org_id: str,
    pm_id: str,
    today: date,
    users: dict,
) -> dict:
    """Crea proyecto marketing360 demo; retorna stats."""
    for email, nombre in M360_USERS:
        users[email] = ensure_user(email, nombre)

    project = create_project(
        token,
        org_id,
        pm_id,
        nombre=PROJECT_NAME,
        descripcion="Pack Marketing 360° — briefing, kanban 7 estados, calendario y aprobaciones",
        pack_slug="marketing360",
        template_slug="t1_cliente_clasico",
        fecha_inicio=add_days(today, -7),
        fecha_fin=add_days(today, 90),
    )

    for email, rol in MEMBER_ROLES:
        uid = users[email]["id"]
        add_member(project["id"], pm_id, uid, rol)

    campana = create_record(
        token,
        project["id"],
        pm_id,
        record_type="campana",
        titulo="Brand Awareness Q3 2026",
        fecha_inicio=add_days(today, -7),
        fecha_fin=add_days(today, 90),
        data={
            "objetivo": "awareness",
            "buyer_persona": "CMO y marketing managers B2B SaaS, 30-50 años, LATAM",
            "canales": ["meta_ads", "google_ads", "linkedin", "organic_social", "newsletter"],
            "presupuesto_produccion": 45000,
            "presupuesto_pauta": 120000,
            "kpi_exito": "CTR > 3% · Reach 500k",
            "fecha_lanzamiento": add_days(today, 30),
        },
    )

    transition_record(
        token,
        project["id"],
        campana["id"],
        actor_user_id=pm_id,
        action_id="iniciar_produccion",
        ignore_errors=True,
    )

    pieza_ids: dict[str, str] = {}
    cliente_id = users["cliente@center.demo"]["id"]

    for titulo, target_state, canal, formato, assignee_email, pub_offset in PIEZAS:
        assignee_ids = [users[assignee_email]["id"]] if assignee_email else []
        pub_date = add_days(today, pub_offset) if pub_offset is not None else None
        body_data: dict = {"canal": canal, "formato": formato, "prioridad": "media"}
        if pub_date:
            body_data["fecha_publicacion"] = pub_date

        rec = post(
            token,
            f"/projects/{project['id']}/records",
            {
                "actor_user_id": pm_id,
                "record_type": "pieza",
                "titulo": titulo,
                "parent_id": campana["id"],
                "assignee_ids": assignee_ids,
                "data": body_data,
                "fecha_inicio": add_days(today, max(0, (pub_offset or 0) - 5)),
                "fecha_fin": pub_date,
            },
        )
        pieza_ids[titulo] = rec["id"]
        if target_state != "backlog":
            advance_pieza(token, project["id"], rec["id"], pm_id, cliente_id, target_state)

    banners_id = pieza_ids.get("Banners display set A")
    meta_ads_id = pieza_ids.get("Subir anuncios Meta")
    if banners_id and meta_ads_id:
        create_dependency(token, project["id"], pm_id, banners_id, meta_ads_id)

    return {
        "nombre": project["nombre"],
        "pack": "marketing360",
        "records": 1 + len(PIEZAS),
        "project_id": project["id"],
    }


def main() -> int:
    wait_for_api()
    today = date.today()
    users: dict = {}
    pm = ensure_user("pm@center.demo", "Ana PM")
    users["pm@center.demo"] = pm
    users["cliente@center.demo"] = ensure_user("cliente@center.demo", "Clara Cliente")

    auth = login(pm["email"])
    token = auth["access_token"]
    org_id = auth.get("organization_id")
    if not org_id:
        org = post(token, "/organizations", {"nombre": "Center Demo", "slug": "center-demo"})
        org_id = org["id"]
        auth = login(pm["email"])
        token = auth["access_token"]

    stats = seed_marketing360_project(token, org_id, pm["id"], today, users)
    print(f"[seed] Marketing 360° OK — {stats['nombre']} ({stats['records']} registros)")
    print(f"  Password: {DEMO_PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
