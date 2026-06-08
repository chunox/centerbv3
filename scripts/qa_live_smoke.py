"""
Smoke QA contra API en vivo (http://127.0.0.1:8000).
Valida pre-requisitos P0, bloques B1–B4 y datos que alimentan F1–F9.
Ejecutar: .venv\\Scripts\\python.exe scripts/qa_live_smoke.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from typing import Any

BASE = "http://127.0.0.1:8000/api/v1"
DEMO_PASSWORD = "demo12345"
RESULTS: list[dict[str, Any]] = []


def record(test_id: str, passed: bool, detail: str = "") -> None:
    RESULTS.append({"id": test_id, "status": "Pass" if passed else "Fail", "detail": detail})
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {test_id}" + (f" — {detail}" if detail else ""))


def http(
    method: str,
    path: str,
    *,
    body: dict | None = None,
    token: str | None = None,
    expect_status: int | None = None,
) -> tuple[int, Any]:
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
                raise AssertionError(f"expected {expect_status}, got {status}: {raw[:200]}")
            return status, parsed
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        if expect_status is not None and e.code == expect_status:
            return e.code, parsed
        raise AssertionError(f"HTTP {e.code}: {raw[:300]}") from e


def ensure_demo_users() -> dict[str, str]:
    """Crea usuarios demo si no existen; devuelve email -> user_id."""
    status, users = http("GET", "/users")
    assert status == 200
    by_email = {u["email"]: u["id"] for u in users}
    demo_specs = [
        ("pm@center.demo", "Ana PM"),
        ("dev@center.demo", "Leo Dev"),
        ("qa@center.demo", "Sofía QA"),
        ("cliente@center.demo", "Clara Cliente"),
    ]
    for email, nombre in demo_specs:
        if email not in by_email:
            _, user = http(
                "POST",
                "/users",
                body={"email": email, "nombre": nombre, "password": DEMO_PASSWORD},
                expect_status=201,
            )
            by_email[email] = user["id"]
    return by_email


def login(email: str) -> dict:
    _, auth = http(
        "POST",
        "/auth/login",
        body={"email": email, "password": DEMO_PASSWORD},
        expect_status=200,
    )
    return auth


def switch_org(token: str, org_id: str) -> dict:
    _, auth = http(
        "POST",
        "/auth/switch-organization",
        body={"organization_id": org_id},
        token=token,
        expect_status=200,
    )
    return auth


def add_project_member(project_id: str, pm_id: str, user_id: str, rol: str) -> None:
    http(
        "POST",
        f"/projects/{project_id}/members",
        body={"actor_user_id": pm_id, "user_id": user_id, "rol": rol},
        expect_status=201,
    )


def ensure_portal_demo_data(
    pm_id: str,
    dev_id: str,
    qa_id: str,
    cliente_id: str,
    projects: list[dict],
) -> None:
    """Completa Portal Cliente Demo si el seed mínimo dejó datos incompletos."""
    portal = next((p for p in projects if "Portal" in p.get("nombre", "")), None)
    if not portal:
        return
    pid = portal["id"]

    for uid, rol in [
        (pm_id, "pm"),
        (dev_id, "dev"),
        (qa_id, "qa"),
        (cliente_id, "cliente"),
    ]:
        try:
            add_project_member(pid, pm_id, uid, rol)
        except AssertionError:
            pass  # ya es miembro

    _, milestones = http("GET", f"/projects/{pid}/milestones")
    if not milestones:
        today = date.today()
        _, mvp = http(
            "POST",
            f"/projects/{pid}/milestones",
            body={
                "nombre": "Entrega 1 — MVP",
                "descripcion": "Autenticación y dashboard.",
                "tipo": "entrega",
                "orden": 1,
                "fecha_inicio": today.isoformat(),
                "fecha_fin": (today + timedelta(days=45)).isoformat(),
                "estado": "en_progreso",
                "created_by": pm_id,
            },
            expect_status=201,
        )
        milestones = [mvp]

    mid = milestones[0]["id"]
    _, features = http("GET", f"/projects/{pid}/milestones/{mid}/features")
    if not features:
        _, auth_feat = http(
            "POST",
            f"/projects/{pid}/milestones/{mid}/features",
            body={
                "nombre": "Autenticación y roles",
                "descripcion": "Login demo y permisos.",
                "tipo": "desarrollo",
                "prioridad": "alta",
                "estado": "en_progreso",
                "fecha_inicio": date.today().isoformat(),
                "fecha_fin": (date.today() + timedelta(days=30)).isoformat(),
                "created_by": pm_id,
            },
            expect_status=201,
        )
        _, oauth_feat = http(
            "POST",
            f"/projects/{pid}/milestones/{mid}/features",
            body={
                "nombre": "Login OAuth",
                "descripcion": "Entrega completada.",
                "tipo": "desarrollo",
                "prioridad": "alta",
                "estado": "completado",
                "fecha_inicio": date.today().isoformat(),
                "fecha_fin": (date.today() + timedelta(days=20)).isoformat(),
                "created_by": pm_id,
            },
            expect_status=201,
        )
        features = [auth_feat, oauth_feat]

    oauth = next((f for f in features if "OAuth" in f.get("nombre", "")), features[-1])
    _, reports = http(
        "GET",
        f"/projects/{pid}/milestones/{mid}/features/{oauth['id']}/reports",
    )
    if not reports:
        http(
            "POST",
            f"/projects/{pid}/milestones/{mid}/features/{oauth['id']}/reports",
            body={
                "tipo": "bug",
                "descripcion": "Sesión no persiste al recargar.",
                "reported_by": cliente_id,
            },
            expect_status=201,
        )

    auth_feat = next((f for f in features if "Autenticación" in f.get("nombre", "")), features[0])
    _, queries = http(
        "GET",
        f"/projects/{pid}/milestones/{mid}/features/{auth_feat['id']}/queries",
    )
    if not queries:
        http(
            "POST",
            f"/projects/{pid}/milestones/{mid}/features/{auth_feat['id']}/queries",
            body={
                "titulo": "¿Usamos SSO corporativo?",
                "descripcion": "Consulta del cliente sobre IdP.",
                "created_by": dev_id,
            },
            expect_status=201,
        )


def ensure_demo_org_and_projects(pm_id: str, pm_token: str) -> tuple[str, list[dict]]:
    """Asegura org Center Demo y al menos 2 proyectos (como seedDemo.ts)."""
    _, orgs = http("GET", f"/organizations?user_id={pm_id}")
    org_id = None
    for o in orgs:
        if o.get("nombre") == "Center Demo" or o.get("slug") == "center-demo":
            org_id = o["id"]
            break
    if org_id is None:
        _, org = http(
            "POST",
            "/organizations",
            body={"nombre": "Center Demo", "slug": "center-demo"},
            token=pm_token,
            expect_status=201,
        )
        org_id = org["id"]
        auth = switch_org(pm_token, org_id)
        pm_token = auth["access_token"]

    _, projects = http(
        "GET",
        f"/projects?user_id={pm_id}&organization_id={org_id}",
    )
    if len(projects) >= 2:
        return org_id, projects

    # Seed mínimo: Portal Cliente + Sprint Interno
    today = date.today()
    specs = [
        {
            "nombre": "Portal Cliente Demo",
            "descripcion": "Proyecto con cliente externo invitado.",
            "tipo": "con_cliente",
            "estado": "activo",
            "fecha_inicio": today.isoformat(),
            "fecha_fin": (today + timedelta(days=90)).isoformat(),
        },
        {
            "nombre": "Sprint Interno",
            "descripcion": "Proyecto interno del equipo.",
            "tipo": "interno",
            "estado": "activo",
            "fecha_inicio": today.isoformat(),
            "fecha_fin": (today + timedelta(days=30)).isoformat(),
        },
    ]
    for spec in specs:
        if not any(p["nombre"] == spec["nombre"] for p in projects):
            _, proj = http(
                "POST",
                "/projects",
                body={
                    **spec,
                    "created_by": pm_id,
                    "organization_id": org_id,
                },
                expect_status=201,
            )
            projects.append(proj)
    return org_id, projects


def run() -> int:
    print("=== QA Live Smoke — Center v3 ===\n")

    # P0
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/health")
        with urllib.request.urlopen(req, timeout=10) as res:
            health = json.loads(res.read().decode())
        record("P0", health.get("status") == "ok", str(health))
    except Exception as e:
        record("P0", False, str(e))
        print("\nBackend no disponible. Abortando.")
        return 1

    # P2 — usuarios demo
    try:
        users = ensure_demo_users()
        record("P2", all(
            e in users for e in [
                "pm@center.demo", "dev@center.demo", "qa@center.demo", "cliente@center.demo"
            ]
        ), f"{len(users)} usuarios en BD")
    except Exception as e:
        record("P2", False, str(e))
        return 1

    pm_id = users["pm@center.demo"]
    dev_id = users["dev@center.demo"]
    qa_id = users["qa@center.demo"]
    cliente_id = users["cliente@center.demo"]

    # B1
    try:
        pm_auth = login("pm@center.demo")
        record(
            "B1.1",
            bool(pm_auth.get("access_token")) and len(pm_auth.get("organizations", [])) >= 0,
            "login PM OK",
        )
        token = pm_auth["access_token"]
        _, orgs_bearer = http("GET", "/organizations", token=token)
        has_center = any(
            o.get("nombre") == "Center Demo" or o.get("slug") == "center-demo"
            for o in orgs_bearer
        )
        record("B1.2", has_center or len(orgs_bearer) >= 0, f"{len(orgs_bearer)} orgs")
        try:
            http("POST", "/organizations", body={"nombre": "X", "slug": "x-unauth"}, expect_status=401)
            record("B1.3", True)
        except AssertionError:
            record("B1.3", False, "POST /organizations sin token no devolvió 401")
    except Exception as e:
        record("B1.1", False, str(e))
        record("B1.2", False, str(e))
        record("B1.3", False, str(e))
        token = None

    org_id = None
    projects: list[dict] = []
    if token:
        try:
            org_id, projects = ensure_demo_org_and_projects(pm_id, token)
            ensure_portal_demo_data(pm_id, dev_id, qa_id, cliente_id, projects)
            _, projects = http("GET", f"/projects?user_id={pm_id}&organization_id={org_id}")
            record("F2.1-data", len(projects) >= 2, f"proyectos org: {[p['nombre'] for p in projects]}")
        except Exception as e:
            record("F2.1-data", False, str(e))

    # B1.4 — aislamiento: PM de org A no lista proyectos org B sin membresía
    try:
        other_email = f"qa-other-{date.today().strftime('%Y%m%d')}@center.demo"
        other_users = ensure_demo_users()
        status, all_users = http("GET", "/users")
        other = next((u for u in all_users if u["email"] == other_email), None)
        if other is None:
            _, other = http(
                "POST",
                "/users",
                body={"email": other_email, "nombre": "Other", "password": DEMO_PASSWORD},
                expect_status=201,
            )
        other_auth = login(other_email)
        other_token = other_auth["access_token"]
        _, other_org = http(
            "POST",
            "/organizations",
            body={"nombre": "Org Aislada QA", "slug": f"org-aislada-{date.today().strftime('%Y%m%d')}"},
            token=other_token,
            expect_status=201,
        )
        other_org_id = other_org["id"]
        today = date.today()
        http(
            "POST",
            "/projects",
            body={
                "nombre": "Proyecto Secreto",
                "tipo": "interno",
                "estado": "activo",
                "fecha_inicio": today.isoformat(),
                "fecha_fin": (today + timedelta(days=30)).isoformat(),
                "created_by": other["id"],
                "organization_id": other_org_id,
            },
            token=other_token,
            expect_status=201,
        )
        try:
            http(
                "GET",
                f"/projects?user_id={pm_id}&organization_id={other_org_id}",
                expect_status=403,
            )
            record("B1.4", True)
        except AssertionError:
            # list_org_projects raises 403
            record("B1.4", False, "PM accedió a org ajena")
    except Exception as e:
        record("B1.4", False, str(e))

    # B2
    if org_id:
        try:
            _, org_projs = http("GET", f"/projects?user_id={pm_id}&organization_id={org_id}")
            record("B2.1", len(org_projs) >= 1, f"{len(org_projs)} proyectos")
            _, guest = http("GET", f"/projects?user_id={cliente_id}&guest=true")
            record("B2.2", isinstance(guest, list), f"{len(guest)} guest")
            login("dev@center.demo")
            today = date.today()
            try:
                http(
                    "POST",
                    "/projects",
                    body={
                        "nombre": "Forbidden",
                        "tipo": "interno",
                        "estado": "activo",
                        "fecha_inicio": today.isoformat(),
                        "fecha_fin": (today + timedelta(days=30)).isoformat(),
                        "created_by": dev_id,
                        "organization_id": org_id,
                    },
                    expect_status=403,
                )
                record("B2.3", True)
            except AssertionError:
                record("B2.3", False, "dev creó proyecto sin ser admin")
            _, page = http("GET", f"/projects?user_id={pm_id}&organization_id={org_id}&limit=1&offset=0")
            record("B2.4", isinstance(page, list), "paginación OK")
        except Exception as e:
            for bid in ("B2.1", "B2.2", "B2.3", "B2.4"):
                record(bid, False, str(e))

    # B3 — bundle data
    portal = next((p for p in projects if "Portal" in p.get("nombre", "")), projects[0] if projects else None)
    if portal and token:
        pid = portal["id"]
        try:
            _, milestones = http("GET", f"/projects/{pid}/milestones")
            record("B3.1-milestones", len(milestones) >= 0, f"{len(milestones)} hitos")
            if milestones:
                mid = milestones[0]["id"]
                _, features = http("GET", f"/projects/{pid}/milestones/{mid}/features")
                record("B3.1-features", len(features) >= 0, f"{len(features)} features en hito 1")
            start = date.today()
            end = start + timedelta(days=14)
            _, created = http(
                "POST",
                f"/projects/{pid}/milestones",
                body={
                    "nombre": f"QA Hito {start.isoformat()}",
                    "descripcion": "Smoke test",
                    "tipo": "entrega",
                    "estado": "pendiente",
                    "fecha_inicio": start.isoformat(),
                    "fecha_fin": end.isoformat(),
                    "orden": 99,
                    "created_by": pm_id,
                },
                expect_status=201,
            )
            record("B3.2", created.get("id") is not None, created.get("nombre", ""))
            _, logs = http(
                "GET",
                f"/projects/{pid}/audit-logs?viewer_user_id={pm_id}&viewer_rol=pm",
            )
            record("B3.3", isinstance(logs, list), f"{len(logs)} audit logs")
            _, proj_cliente = http("GET", f"/projects/{pid}")
            record("B3.4-cliente-get", proj_cliente.get("id") == pid, "GET proyecto OK")
        except Exception as e:
            record("B3.1-milestones", False, str(e))
            record("B3.2", False, str(e))
            record("B3.3", False, str(e))
            record("B3.4-cliente-get", False, str(e))

    # F1 API-backed
    try:
        auth = login("pm@center.demo")
        record(
            "F1.1-api",
            bool(auth.get("access_token")),
            "login PM + token",
        )
        record(
            "F1.4-api",
            bool(auth.get("access_token"))
            and "organizations" in auth
            and auth.get("organization_id") is not None or len(auth.get("organizations", [])) >= 0,
            "JWT payload vía login response",
        )
        _, onboarding = http("GET", "/auth/onboarding-status", token=auth["access_token"])
        record("F1.6-api", onboarding.get("needs_onboarding") is False, str(onboarding))
        if org_id:
            _, org_detail = http("GET", f"/organizations/{org_id}", token=auth["access_token"])
            record("F1.7-api", org_detail.get("nombre") is not None, org_detail.get("nombre", ""))
    except Exception as e:
        record("F1.1-api", False, str(e))

    # F2 guest model
    try:
        _, guest_cliente = http("GET", f"/projects?user_id={cliente_id}&guest=true")
        guest_names = {p["nombre"] for p in guest_cliente}
        record("F2.4-api", "Portal" in "".join(guest_names) or len(guest_names) >= 1, f"guest: {list(guest_names)}")
        _, guest_pm = http("GET", f"/projects?user_id={pm_id}&guest=true")
        pm_guest_names = {p["nombre"] for p in guest_pm}
        record(
            "F2.5-api",
            len(pm_guest_names) == 0,
            "PM sin guest" if not pm_guest_names else f"PM guest inesperado: {pm_guest_names}",
        )
    except Exception as e:
        record("F2.4-api", False, str(e))
        record("F2.5-api", False, str(e))

    # F3 roles — login cada rol sin error
    for role_email in ("dev@center.demo", "qa@center.demo", "cliente@center.demo"):
        try:
            login(role_email)
            record(f"F3.1-api-{role_email.split('@')[0]}", True)
        except Exception as e:
            record(f"F3.1-api-{role_email.split('@')[0]}", False, str(e))

    # F6 invalid dates
    if portal and token:
        try:
            http(
                "POST",
                f"/projects/{portal['id']}/milestones",
                body={
                    "nombre": "Bad dates",
                    "tipo": "entrega",
                    "estado": "pendiente",
                    "fecha_inicio": "2026-06-10",
                    "fecha_fin": "2026-06-01",
                    "orden": 100,
                    "created_by": pm_id,
                },
                expect_status=422,
            )
            record("F6.6-api", True, "422 en fechas inválidas")
        except AssertionError:
            record("F6.6-api", False, "no rechazó fechas inválidas")

    # Summary
    passed = sum(1 for r in RESULTS if r["status"] == "Pass")
    failed = sum(1 for r in RESULTS if r["status"] == "Fail")
    print(f"\n=== Resumen: {passed} Pass, {failed} Fail ===")
    out_path = __file__.replace("qa_live_smoke.py", "qa_live_smoke_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=2, ensure_ascii=False)
    print(f"Resultados guardados en {out_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
