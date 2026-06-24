"""
seed_demo.py — Crea datos demo para desarrollo local.

Proyectos:
  - Software Demo (waterfall, pack=software-waterfall, template=t3_interno_clasico)
  - Scrum Demo    (scrum,     pack=software-scrum,     template=t6_scrum_interno)

Uso:
    cd proyecto-central-backend-v3
    .\.venv\Scripts\python.exe scripts/seed_demo.py
    .\.venv\Scripts\python.exe scripts/seed_demo.py --reset
"""
import argparse
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_engine, get_session_factory
from app.models.entities import Base, Organization, OrganizationMember, Project, ProjectMember, ProjectRecord, ProjectRole, User
from app.services.auth_service import hash_password


# ─── Datos constantes ────────────────────────────────────────────────────────

DEMO_USERS = [
    {"nombre": "PM Demo",      "email": "pm@center.demo",      "password": "demo12345"},
    {"nombre": "Dev Demo",     "email": "dev@center.demo",     "password": "demo12345"},
    {"nombre": "Dev2 Demo",    "email": "dev2@center.demo",    "password": "demo12345"},
    {"nombre": "QA Demo",      "email": "qa@center.demo",      "password": "demo12345"},
    {"nombre": "Cliente Demo", "email": "cliente@center.demo", "password": "demo12345"},
]

ORG_NOMBRE = "Center Demo"
ORG_SLUG   = "center-demo"

ROLES = [
    {"slug": "pm",        "nombre": "Project Manager", "color": "#6366f1"},
    {"slug": "tech_lead", "nombre": "Tech Lead",       "color": "#0ea5e9"},
    {"slug": "dev",       "nombre": "Desarrollador",   "color": "#10b981"},
    {"slug": "qa",        "nombre": "QA",              "color": "#f59e0b"},
    {"slug": "cliente",   "nombre": "Cliente",         "color": "#ef4444"},
]

USER_PROJECT_ROLES = {
    "pm@center.demo":      "pm",
    "dev@center.demo":     "dev",
    "dev2@center.demo":    "dev",
    "qa@center.demo":      "qa",
    "cliente@center.demo": "cliente",
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def reset_db():
    print("[!] Dropping and recreating all tables...")
    eng = get_engine()
    Base.metadata.drop_all(bind=eng)
    Base.metadata.create_all(bind=eng)
    print("[OK] Tables recreated.")


def seed_users(db) -> dict:
    users = {}
    for u in DEMO_USERS:
        existing = db.query(User).filter(User.email == u["email"]).first()
        if existing:
            existing.password_hash = hash_password(u["password"])
            existing.is_active = True
            db.flush()
            print(f"  ~ usuario resetado: {u['email']}")
            users[u["email"]] = existing
        else:
            user = User(nombre=u["nombre"], email=u["email"], password_hash=hash_password(u["password"]))
            db.add(user)
            db.flush()
            users[u["email"]] = user
            print(f"  + usuario creado: {u['email']}")
    return users


def seed_org(db, users: dict) -> Organization:
    org = db.query(Organization).filter(Organization.slug == ORG_SLUG).first()
    if not org:
        org = Organization(nombre=ORG_NOMBRE, slug=ORG_SLUG)
        db.add(org)
        db.flush()
        print(f"  + org creada: {ORG_NOMBRE}")
    else:
        print(f"  ~ org ya existe: {ORG_NOMBRE}")

    pm = users["pm@center.demo"]
    for email, user in users.items():
        exists = db.query(OrganizationMember).filter(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.user_id == user.id,
        ).first()
        if not exists:
            rol = "owner" if email == "pm@center.demo" else "member"
            db.add(OrganizationMember(organization_id=org.id, user_id=user.id, rol=rol))
            print(f"    + miembro org: {email}")
    return org


def seed_project(db, org: Organization, users: dict, nombre: str, pack_slug: str, template_slug: str, delivery_mode: str) -> tuple:
    """Crea proyecto + roles + membresías. Retorna (project, role_map)."""
    pm_user = users["pm@center.demo"]

    project = db.query(Project).filter(
        Project.organization_id == org.id,
        Project.nombre == nombre,
    ).first()

    if not project:
        project = Project(
            organization_id=org.id,
            nombre=nombre,
            descripcion=f"Proyecto demo — {delivery_mode}",
            pack_slug=pack_slug,
            template_slug=template_slug,
            delivery_mode=delivery_mode,
            estado="activo",
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 12, 31),
            settings={},
            created_by=pm_user.id,
        )
        db.add(project)
        db.flush()
        print(f"  + proyecto creado: {nombre}")
    else:
        # Asegurar que el pack y template sean correctos
        project.pack_slug = pack_slug
        project.template_slug = template_slug
        db.flush()
        print(f"  ~ proyecto ya existe: {nombre} (pack actualizado)")

    # Roles
    role_map = {}
    for r in ROLES:
        role = db.query(ProjectRole).filter(
            ProjectRole.project_id == project.id,
            ProjectRole.slug == r["slug"],
        ).first()
        if not role:
            role = ProjectRole(project_id=project.id, slug=r["slug"], nombre=r["nombre"], color=r["color"])
            db.add(role)
            db.flush()
        role_map[r["slug"]] = role

    # Membresías
    for email, user in users.items():
        role_slug = USER_PROJECT_ROLES.get(email, "dev")
        role = role_map[role_slug]
        exists = db.query(ProjectMember).filter(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
        ).first()
        if not exists:
            db.add(ProjectMember(project_id=project.id, user_id=user.id, role_id=role.id))

    return project, role_map


def _make_record(db, project_id: str, actor_id: str, record_type: str, title: str,
                 status: str, orden: int, parent_id: str | None = None, extra: dict | None = None,
                 estimacion: float | None = None) -> ProjectRecord:
    existing = db.query(ProjectRecord).filter(
        ProjectRecord.project_id == project_id,
        ProjectRecord.title == title,
        ProjectRecord.record_type == record_type,
    ).first()
    if existing:
        return existing
    r = ProjectRecord(
        project_id=project_id,
        record_type=record_type,
        title=title,
        status=status,
        orden=orden,
        parent_id=parent_id,
        extra=extra or {},
        estimacion=estimacion,
        created_by=actor_id,
    )
    db.add(r)
    db.flush()
    return r


def seed_waterfall_records(db, project: Project, pm_id: str):
    """Hitos, features y tareas para el proyecto waterfall."""
    p = project.id

    # Hito 1
    m1 = _make_record(db, p, pm_id, "milestone", "MVP - Core Features",         "en_progreso", 10)
    f1 = _make_record(db, p, pm_id, "feature",   "Autenticacion de usuarios",    "done",        10, m1.id)
    f2 = _make_record(db, p, pm_id, "feature",   "Dashboard de proyectos",       "en_progreso", 20, m1.id)
    f3 = _make_record(db, p, pm_id, "feature",   "Gestion de registros",         "pendiente",   30, m1.id)
    _make_record(db, p, pm_id, "task", "Disenar modelo de datos",       "done",        10, f1.id)
    _make_record(db, p, pm_id, "task", "Implementar JWT auth",          "done",        20, f1.id)
    _make_record(db, p, pm_id, "task", "UI de login y registro",        "done",        30, f1.id)
    _make_record(db, p, pm_id, "task", "Endpoint listado proyectos",    "en_progreso", 10, f2.id)
    _make_record(db, p, pm_id, "task", "Componente ProjectCard",        "en_progreso", 20, f2.id)
    _make_record(db, p, pm_id, "task", "API records CRUD",              "pendiente",   10, f3.id)

    # Hito 2
    m2 = _make_record(db, p, pm_id, "milestone", "Beta - Flujos de trabajo",    "pendiente",   20)
    f4 = _make_record(db, p, pm_id, "feature",   "Kanban board",                "pendiente",   10, m2.id)
    f5 = _make_record(db, p, pm_id, "feature",   "Transiciones de estado",      "pendiente",   20, m2.id)
    _make_record(db, p, pm_id, "task", "Columnas drag-and-drop",        "pendiente",   10, f4.id)
    _make_record(db, p, pm_id, "task", "Motor de workflow",             "pendiente",   10, f5.id)

    print(f"    + registros waterfall creados")


def seed_scrum_records(db, project: Project, pm_id: str):
    """Sprints, epics e historias para el proyecto scrum."""
    p = project.id

    # Product Backlog container
    backlog = _make_record(db, p, pm_id, "task", "Product Backlog", "activo", 0, extra={"scrum_role": "backlog"})

    # Épicas
    e1 = _make_record(db, p, pm_id, "task", "Autenticacion y onboarding", "en_progreso", 10, backlog.id, {"scrum_role": "epic"})
    e2 = _make_record(db, p, pm_id, "task", "Gestion de proyectos",       "product_backlog", 20, backlog.id, {"scrum_role": "epic"})
    e3 = _make_record(db, p, pm_id, "task", "Modo Scrum",                 "product_backlog", 30, backlog.id, {"scrum_role": "epic"})

    # Sprint 1 (activo)
    s1 = _make_record(db, p, pm_id, "sprint", "Sprint 1 - Auth", "activo", 10,
                      extra={"goal": "Completar flujo completo de autenticacion y onboarding"},
                      estimacion=None)
    s1.fecha_inicio = date(2026, 6, 1)
    s1.fecha_fin    = date(2026, 6, 14)

    # Sprint 2 (pendiente)
    s2 = _make_record(db, p, pm_id, "sprint", "Sprint 2 - Dashboard", "pendiente", 20,
                      extra={"goal": "Listado de proyectos y acceso al contexto del proyecto"})
    s2.fecha_inicio = date(2026, 6, 15)
    s2.fecha_fin    = date(2026, 6, 28)

    # Historias en Sprint 1 (parent_id = sprint)
    _make_record(db, p, pm_id, "task", "Como usuario quiero registrarme",         "completado",   10, s1.id, {"scrum_role": "story", "original_parent_id": e1.id}, 5)
    _make_record(db, p, pm_id, "task", "Como usuario quiero iniciar sesion",      "completado",   20, s1.id, {"scrum_role": "story", "original_parent_id": e1.id}, 3)
    _make_record(db, p, pm_id, "task", "Como usuario quiero recuperar password",  "en_progreso",  30, s1.id, {"scrum_role": "story", "original_parent_id": e1.id}, 5)
    _make_record(db, p, pm_id, "task", "Como PM quiero ver mis organizaciones",   "en_revision",  40, s1.id, {"scrum_role": "story", "original_parent_id": e2.id}, 3)

    # Historias en backlog (parent_id = epic, sin sprint)
    _make_record(db, p, pm_id, "task", "Como dev quiero ver el access-context",   "product_backlog", 10, e2.id, {"scrum_role": "story"}, 8)
    _make_record(db, p, pm_id, "task", "Como PM quiero crear un proyecto",        "product_backlog", 20, e2.id, {"scrum_role": "story"}, 5)
    _make_record(db, p, pm_id, "task", "Como dev quiero ver el product backlog",  "product_backlog", 10, e3.id, {"scrum_role": "story"}, 8)
    _make_record(db, p, pm_id, "task", "Como dev quiero ver el sprint board",     "product_backlog", 20, e3.id, {"scrum_role": "story"}, 5)

    print(f"    + registros scrum creados")


def seed(db):
    print("\n== Usuarios ==")
    users = seed_users(db)
    pm_id = users["pm@center.demo"].id

    print("\n== Organizacion ==")
    org = seed_org(db, users)

    print("\n== Proyecto Waterfall ==")
    wf_project, _ = seed_project(
        db, org, users,
        nombre="Software Demo",
        pack_slug="software-waterfall",
        template_slug="t3_interno_clasico",
        delivery_mode="waterfall",
    )
    seed_waterfall_records(db, wf_project, pm_id)

    print("\n== Proyecto Scrum ==")
    scrum_project, _ = seed_project(
        db, org, users,
        nombre="Scrum Demo",
        pack_slug="software-scrum",
        template_slug="t6_scrum_interno",
        delivery_mode="scrum",
    )
    seed_scrum_records(db, scrum_project, pm_id)

    db.commit()

    print("\n[OK] Seed completado.")
    print("\nUsuarios demo (password: demo12345):")
    for u in DEMO_USERS:
        print(f"  {u['email']}")
    print(f"\nOrg ID:             {org.id}")
    print(f"Proyecto Waterfall: {wf_project.id}")
    print(f"Proyecto Scrum:     {scrum_project.id}")


def main():
    parser = argparse.ArgumentParser(description="Seed demo data")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables")
    args = parser.parse_args()

    if args.reset:
        reset_db()

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
