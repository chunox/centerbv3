"""Verificación rápida de proyectos Scrum (épicas, sprint_id, métricas en horas)."""
import json
import urllib.error
import urllib.request


def req(method, path, token=None, body=None):
    url = f"http://127.0.0.1:8000/api/v1{path}"
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    d = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=d, headers=h, method=method)
    try:
        with urllib.request.urlopen(r) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        print(f"  HTTP {e.code}: {detail[:300]}")
        return None


auth = req("POST", "/auth/login", body={"email": "pm@center.demo", "password": "demo12345"})
token = auth["access_token"]
pm_id = auth["user"]["id"]

projects = req("GET", "/projects", token=token)
scrum_projects = [
    (p["id"], p["nombre"], p.get("template_slug"))
    for p in (projects or [])
    if p.get("template_slug") in ("t6_scrum_interno", "t7_scrum_cliente")
]

if not scrum_projects:
    print("No hay proyectos Scrum en la BD. Ejecuta seed_scrum_duo.py o seed_scrum_rich.py.")
    raise SystemExit(0)

for pid, name, tpl in scrum_projects[:5]:
    ctx = req("GET", f"/projects/{pid}/access-context?actor_user_id={pm_id}", token=token)
    wbs = ctx.get("workbenches") or []
    scrum_keys = [w["key"] for w in wbs if "sprint" in w["key"] or "backlog" in w["key"] or "planning" in w["key"]]
    print(f"{name} ({tpl})")
    print(f"  scrum workbenches: {scrum_keys}")

    epics = req("GET", f"/projects/{pid}/records?record_type=epic&actor_user_id={pm_id}", token=token)
    print(f"  epics: {len(epics or [])}")

    sprints = req("GET", f"/projects/{pid}/scrum/sprints?actor_user_id={pm_id}", token=token)
    if sprints:
        for s in sprints:
            title = s["titulo"].encode("ascii", "replace").decode()
            horas_plan = s.get("horas_planeadas") or s.get("velocidad_planeada")
            horas_done = s.get("horas_completadas") or s.get("velocidad_real")
            print(f"  sprint: {title} ({s['estado']}, {horas_plan}h plan / {horas_done}h done)")

    all_feat = req("GET", f"/projects/{pid}/records?record_type=feature&actor_user_id={pm_id}", token=token)
    if all_feat is not None:
        estados: dict[str, int] = {}
        with_sprint = 0
        with_epic_parent = 0
        epic_ids = {e["id"] for e in (epics or [])}
        for f in all_feat:
            e = f["estado"]
            estados[e] = estados.get(e, 0) + 1
            if f.get("data", {}).get("sprint_id"):
                with_sprint += 1
            if f.get("parent_id") in epic_ids:
                with_epic_parent += 1
        print(f"  features by state: {dict(sorted(estados.items()))}")
        print(f"  features with sprint_id: {with_sprint}, parent=epic: {with_epic_parent}")

    backlog = req(
        "GET",
        f"/projects/{pid}/records?record_type=feature&estado=product_backlog&actor_user_id={pm_id}",
        token=token,
    )
    if backlog is not None:
        print(f"  backlog (estado filter): {len(backlog)} items")
    print()
