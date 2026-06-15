import json, urllib.request, urllib.error

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

PROJECTS = [
    ("827ba2d6-5364-4c98-b911-570fe057d16f", "CRM Platform (t6)"),
    ("e8dc2010-2b18-42e9-990c-08ab79e45d1b", "E-commerce (t7)"),
]

for pid, name in PROJECTS:
    ctx = req("GET", f"/projects/{pid}/access-context?actor_user_id={pm_id}", token=token)
    wbs = ctx.get("workbenches") or []
    scrum_keys = [w["key"] for w in wbs if "sprint" in w["key"] or "backlog" in w["key"] or "planning" in w["key"]]
    print(f"{name}")
    print(f"  scrum workbenches: {scrum_keys}")
    sprints = req("GET", f"/projects/{pid}/scrum/sprints?actor_user_id={pm_id}", token=token)
    if sprints:
        for s in sprints:
            title = s["titulo"].encode("ascii","replace").decode()
            print(f"  sprint: {title} ({s['estado']}, vel={s['velocidad_planeada']} SP)")

    # All features (no estado filter)
    all_feat = req("GET", f"/projects/{pid}/records?record_type=feature&actor_user_id={pm_id}", token=token)
    if all_feat is not None:
        estados = {}
        for f in all_feat:
            e = f["estado"]
            estados[e] = estados.get(e, 0) + 1
        print(f"  all features by state: {dict(sorted(estados.items()))}")

    # Backlog with estado filter
    backlog = req("GET", f"/projects/{pid}/records?record_type=feature&estado=product_backlog&actor_user_id={pm_id}", token=token)
    if backlog is not None:
        print(f"  backlog (estado filter): {len(backlog)} items")
    print()
