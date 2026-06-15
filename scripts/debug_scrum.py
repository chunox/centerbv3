import json, urllib.request, urllib.error

def api(method, path, token=None, body=None):
    url = f"http://127.0.0.1:8000/api/v1{path}"
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    d = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=d, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

_, auth = api("POST", "/auth/login", body={"email": "pm@center.demo", "password": "demo12345"})
token = auth["access_token"]
pm_id = auth["user"]["id"]

_, projects = api("GET", f"/projects?actor_user_id={pm_id}", token=token)
print("Projects:")
for p in projects:
    print(f"  [{p['template_slug']}] {p['nombre']} — {p['id']}")

print()
print("Testing records endpoint on each project:")
for p in projects:
    pid = p["id"]
    name = p["nombre"]
    status, data = api("GET", f"/projects/{pid}/records?record_type=milestone&actor_user_id={pm_id}", token=token)
    if status == 200:
        print(f"  [OK]  {name} ({status}, {len(data)} milestones)")
    else:
        print(f"  [ERR] {name} ({status}): {str(data)[:100]}")
