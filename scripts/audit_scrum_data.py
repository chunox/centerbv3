"""Auditoría puntual de datos Scrum v2 en BD vs expectativas de seed (solo lectura)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"


def req(method: str, path: str, token: str | None = None, body: dict | None = None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    d = json.dumps(body).encode() if body else None
    r = urllib.request.Request(BASE + path, data=d, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:400]}


def _role(rows: list, role: str) -> list:
    return [r for r in (rows or []) if (r.get("data") or {}).get("scrum_role") == role]


def audit_project(name: str, pid: str, pm_id: str, token: str) -> dict:
    milestones = req("GET", f"/projects/{pid}/records?record_type=milestone&actor_user_id={pm_id}", token=token)
    tasks = req("GET", f"/projects/{pid}/records?record_type=task&actor_user_id={pm_id}", token=token)

    epics = _role(tasks, "epic")
    stories = _role(tasks, "story")
    dev_tasks = _role(tasks, "dev")
    sprint_milestones = [
        m for m in (milestones or [])
        if (m.get("data") or {}).get("tipo") in ("sprint", "entrega")
    ]
    sprint_ids = {m["id"] for m in sprint_milestones}

    backlog = req(
        "GET",
        f"/projects/{pid}/records?record_type=task&in_product_backlog=true&actor_user_id={pm_id}",
        token=token,
    )
    backlog_stories = _role(backlog, "story")

    dev_hours = sum(float((t.get("data") or {}).get("estimacion_horas") or 0) for t in dev_tasks)
    story_hours = sum(float(s.get("esfuerzo_horas") or 0) for s in stories if s.get("esfuerzo_horas"))

    estados: dict[str, int] = {}
    for s in stories:
        estados[s["estado"]] = estados.get(s["estado"], 0) + 1

    sprint_rows = []
    for m in sorted(sprint_milestones, key=lambda x: x.get("orden") or 0):
        sid = m["id"]
        sf = req(
            "GET",
            f"/projects/{pid}/records?record_type=task&sprint_id={sid}&actor_user_id={pm_id}",
            token=token,
        )
        sprint_rows.append({
            "orden": m.get("orden"),
            "titulo": m["titulo"],
            "estado": m["estado"],
            "horas_planeadas": (m.get("data") or {}).get("horas_planeadas"),
            "stories_in_sprint": len(_role(sf, "story")),
        })

    sprints_api = req("GET", f"/projects/{pid}/scrum/sprints?actor_user_id={pm_id}", token=token)
    velocity = req("GET", f"/projects/{pid}/scrum/velocity?actor_user_id={pm_id}&limit=6", token=token)
    impediments = req("GET", f"/projects/{pid}/scrum/impediments?actor_user_id={pm_id}", token=token)
    sessions = req("GET", f"/projects/{pid}/scrum/sessions?actor_user_id={pm_id}", token=token)

    capacity_rows: list[dict] = []
    for m in sprint_milestones:
        cap = req(
            "GET",
            f"/projects/{pid}/scrum/sprints/{m['id']}/capacity?actor_user_id={pm_id}",
            token=token,
        )
        if isinstance(cap, dict) and "_error" in cap:
            continue
        if isinstance(cap, dict):
            capacity_rows.append(
                {
                    "sprint_id": m["id"],
                    "available_horas": cap.get("available_horas"),
                    "capacity_items": len(cap.get("capacity_plan") or []),
                }
            )

    uat_states = {"uat", "ready_for_test", "esperando_liberacion_pm", "esperando_validacion_cliente"}
    uat_stories = [s for s in stories if s["estado"] in uat_states]

    committed = [s for s in stories if s.get("parent_id") in sprint_ids]

    return {
        "name": name,
        "project_id": pid,
        "epic_titles": [e["titulo"] for e in epics],
        "counts": {
            "epics": len(epics),
            "sprints": len(sprint_milestones),
            "stories": len(stories),
            "dev_tasks": len(dev_tasks),
            "committed_stories": len(committed),
            "backlog_stories_api": len(backlog_stories),
            "dev_tasks_with_hours": sum(1 for t in dev_tasks if (t.get("data") or {}).get("estimacion_horas")),
            "dev_hours_sum": round(dev_hours, 1),
            "story_esfuerzo_horas_sum": round(story_hours, 1),
            "uat_stories": len(uat_stories),
            "impediments_total": len(impediments or []) if isinstance(impediments, list) else 0,
            "impediments_open": len(
                [i for i in (impediments or []) if (i.get("data") or {}).get("status") == "open"]
            ) if isinstance(impediments, list) else 0,
            "sessions_total": len(sessions or []) if isinstance(sessions, list) else 0,
        },
        "stories_by_state": estados,
        "sprints": sprint_rows,
        "capacity": capacity_rows,
        "scrum_api_first_sprint": sprints_api[0] if sprints_api and not isinstance(sprints_api, dict) else None,
        "velocity": velocity if not isinstance(velocity, dict) or "_error" not in velocity else velocity,
    }


def main():
    auth = req("POST", "/auth/login", body={"email": "pm@center.demo", "password": "demo12345"})
    if not auth or "_error" in auth:
        print("API no disponible o login falló")
        return
    token = auth["access_token"]
    pm_id = auth["user"]["id"]

    projects = req("GET", "/projects", token=token)
    targets = [
        p for p in (projects or [])
        if p.get("template_slug") in ("t6_scrum_interno", "t7_scrum_cliente")
    ]

    results = []
    for p in sorted(targets, key=lambda x: x["nombre"]):
        results.append(audit_project(p["nombre"], p["id"], pm_id, token))

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
