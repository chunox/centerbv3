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
from app.models.entities import Base, Organization, OrganizationMember, Project, ProjectMember, ProjectRecord, ProjectRecordAssignee, ProjectRole, User
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
    m1 = _make_record(db, p, pm_id, "milestone", "MVP - Core Features",         "in_progress", 10)
    f1 = _make_record(db, p, pm_id, "feature",   "Autenticacion de usuarios",    "done",        10, m1.id)
    f2 = _make_record(db, p, pm_id, "feature",   "Dashboard de proyectos",       "in_progress", 20, m1.id)
    f3 = _make_record(db, p, pm_id, "feature",   "Gestion de registros",         "backlog",     30, m1.id)
    _make_record(db, p, pm_id, "task", "Disenar modelo de datos",       "done",        10, f1.id)
    _make_record(db, p, pm_id, "task", "Implementar JWT auth",          "done",        20, f1.id)
    _make_record(db, p, pm_id, "task", "UI de login y registro",        "done",        30, f1.id)
    _make_record(db, p, pm_id, "task", "Endpoint listado proyectos",    "in_progress", 10, f2.id)
    _make_record(db, p, pm_id, "task", "Componente ProjectCard",        "in_progress", 20, f2.id)
    _make_record(db, p, pm_id, "task", "API records CRUD",              "backlog",     10, f3.id)

    # Hito 2
    m2 = _make_record(db, p, pm_id, "milestone", "Beta - Flujos de trabajo",    "backlog",     20)
    f4 = _make_record(db, p, pm_id, "feature",   "Kanban board",                "backlog",     10, m2.id)
    f5 = _make_record(db, p, pm_id, "feature",   "Transiciones de estado",      "backlog",     20, m2.id)
    _make_record(db, p, pm_id, "task", "Columnas drag-and-drop",        "backlog",     10, f4.id)
    _make_record(db, p, pm_id, "task", "Motor de workflow",             "backlog",     10, f5.id)

    print(f"    + registros waterfall creados")


def _assign(db, record: ProjectRecord, *user_ids):
    """Asigna usuarios a un record (ignora duplicados)."""
    for uid in user_ids:
        exists = db.query(ProjectRecordAssignee).filter(
            ProjectRecordAssignee.record_id == record.id,
            ProjectRecordAssignee.user_id == uid,
        ).first()
        if not exists:
            db.add(ProjectRecordAssignee(record_id=record.id, user_id=uid))
    db.flush()


def seed_scrum_records(db, project: Project, pm_id: str, users: dict):
    """Sprints, epics, historias, dev tasks y subtareas para el proyecto scrum."""
    p      = project.id
    dev_id  = users["dev@center.demo"].id
    dev2_id = users["dev2@center.demo"].id
    qa_id   = users["qa@center.demo"].id

    # ── Product Backlog container ─────────────────────────────────────────────
    backlog = _make_record(db, p, pm_id, "task", "Product Backlog", "activo", 0,
                           extra={"scrum_role": "backlog"})

    # ── Épicas ────────────────────────────────────────────────────────────────
    e1 = _make_record(db, p, pm_id, "task", "Autenticacion y onboarding",    "in_progress", 10, backlog.id, {"scrum_role": "epic"}, 34)
    e2 = _make_record(db, p, pm_id, "task", "Gestion de proyectos",           "in_progress", 20, backlog.id, {"scrum_role": "epic"}, 55)
    e3 = _make_record(db, p, pm_id, "task", "Modo Scrum",                     "backlog",     30, backlog.id, {"scrum_role": "epic"}, 40)
    e4 = _make_record(db, p, pm_id, "task", "Notificaciones y actividad",     "backlog",     40, backlog.id, {"scrum_role": "epic"}, 20)

    # ── Sprint 0 — cerrado ────────────────────────────────────────────────────
    s0 = _make_record(db, p, pm_id, "sprint", "Sprint 0 - Setup", "cerrado", 5,
                      extra={"goal": "Infraestructura base: DB, CI/CD, autenticacion JWT"},
                      estimacion=None)
    s0.fecha_inicio = date(2026, 5, 12)
    s0.fecha_fin    = date(2026, 5, 25)
    db.flush()

    # Historias del sprint 0 (cerradas — parent_id = sprint)
    h_setup1 = _make_record(db, p, pm_id, "task", "Setup inicial del proyecto",          "done",      10, s0.id, {"scrum_role": "story", "original_parent_id": e1.id}, 3)
    h_setup2 = _make_record(db, p, pm_id, "task", "Schema DB y migraciones Alembic",    "done",      20, s0.id, {"scrum_role": "story", "original_parent_id": e1.id}, 5)
    h_setup3 = _make_record(db, p, pm_id, "task", "Autenticacion JWT + refresh token",  "done",      30, s0.id, {"scrum_role": "story", "original_parent_id": e1.id}, 8)
    _assign(db, h_setup1, dev_id)
    _assign(db, h_setup2, dev_id, dev2_id)
    _assign(db, h_setup3, dev_id)

    # Dev tasks del sprint 0
    _make_record(db, p, pm_id, "task", "Crear proyecto FastAPI + estructura",     "done", 10, h_setup1.id, {"scrum_role": "dev"}, 2)
    _make_record(db, p, pm_id, "task", "Configurar Docker Compose + Postgres",    "done", 20, h_setup1.id, {"scrum_role": "dev"}, 1)
    t_alembic = _make_record(db, p, pm_id, "task", "Modelos SQLAlchemy 20 tablas",       "done", 10, h_setup2.id, {"scrum_role": "dev"}, 3)
    _make_record(db, p, pm_id, "task", "Migracion inicial Alembic",               "done", 20, h_setup2.id, {"scrum_role": "dev"}, 1)
    _make_record(db, p, pm_id, "task", "Endpoint POST /auth/login JWT",           "done", 10, h_setup3.id, {"scrum_role": "dev"}, 3)
    _make_record(db, p, pm_id, "task", "Endpoint POST /auth/refresh",             "done", 20, h_setup3.id, {"scrum_role": "dev"}, 2)
    _assign(db, t_alembic, dev2_id)

    # ── Sprint 1 — activo ─────────────────────────────────────────────────────
    s1 = _make_record(db, p, pm_id, "sprint", "Sprint 1 - Auth & Registro", "activo", 10,
                      extra={"goal": "Flujo completo de registro, login y recuperacion de password"},
                      estimacion=None)
    s1.fecha_inicio = date(2026, 6, 2)
    s1.fecha_fin    = date(2026, 6, 20)
    db.flush()

    # ── Historias Sprint 1 ────────────────────────────────────────────────────

    h1 = _make_record(db, p, pm_id, "task", "Como usuario quiero registrarme con email",
                      "done", 10, s1.id, {"scrum_role": "story", "original_parent_id": e1.id}, 5)
    _assign(db, h1, dev_id)
    _make_record(db, p, pm_id, "task", "Endpoint POST /auth/register",        "done",        10, h1.id, {"scrum_role": "dev"}, 2)
    _make_record(db, p, pm_id, "task", "Validaciones de formulario registro",  "done",        20, h1.id, {"scrum_role": "dev"}, 1)
    _make_record(db, p, pm_id, "task", "Pantalla de registro React",           "done",        30, h1.id, {"scrum_role": "dev"}, 2)

    h2 = _make_record(db, p, pm_id, "task", "Como usuario quiero iniciar sesion",
                      "done", 20, s1.id, {"scrum_role": "story", "original_parent_id": e1.id}, 3)
    _assign(db, h2, dev_id)
    _make_record(db, p, pm_id, "task", "Endpoint POST /auth/login",            "done",        10, h2.id, {"scrum_role": "dev"}, 1)
    _make_record(db, p, pm_id, "task", "Persistencia JWT en localStorage",     "done",        20, h2.id, {"scrum_role": "dev"}, 1)
    _make_record(db, p, pm_id, "task", "Redirect post-login al dashboard",     "done",        30, h2.id, {"scrum_role": "dev"}, 1)

    h3 = _make_record(db, p, pm_id, "task", "Como usuario quiero recuperar mi password",
                      "in_review", 30, s1.id, {"scrum_role": "story", "original_parent_id": e1.id}, 5)
    _assign(db, h3, dev2_id)
    _make_record(db, p, pm_id, "task", "Endpoint POST /auth/forgot-password",  "done",        10, h3.id, {"scrum_role": "dev"}, 2)
    _make_record(db, p, pm_id, "task", "Envio de email con token reset",        "in_review",   20, h3.id, {"scrum_role": "dev"}, 3)
    _make_record(db, p, pm_id, "task", "Pantalla reset password",               "done",        30, h3.id, {"scrum_role": "dev"}, 2)

    h4 = _make_record(db, p, pm_id, "task", "Como usuario quiero ver mi perfil",
                      "in_progress", 40, s1.id, {"scrum_role": "story", "original_parent_id": e1.id}, 3)
    _assign(db, h4, dev2_id, qa_id)
    _make_record(db, p, pm_id, "task", "Endpoint GET /users/me",               "done",        10, h4.id, {"scrum_role": "dev"}, 1)
    _make_record(db, p, pm_id, "task", "Pantalla de perfil con avatar",         "in_progress", 20, h4.id, {"scrum_role": "dev"}, 2)
    t_avatar = _make_record(db, p, pm_id, "task", "Upload de avatar a S3",     "to_do",       30, h4.id, {"scrum_role": "dev"}, 3)
    _assign(db, t_avatar, dev2_id)
    # Subtareas de upload avatar
    _make_record(db, p, pm_id, "task", "Configurar bucket S3 en staging",     "done",        10, t_avatar.id, {"scrum_role": "subtask"}, 1)
    _make_record(db, p, pm_id, "task", "Presigned URL endpoint",              "in_progress", 20, t_avatar.id, {"scrum_role": "subtask"}, 2)
    _make_record(db, p, pm_id, "task", "Componente FileUpload React",         "to_do",       30, t_avatar.id, {"scrum_role": "subtask"}, 1)

    h5 = _make_record(db, p, pm_id, "task", "Como PM quiero ver mis organizaciones",
                      "to_do", 50, s1.id, {"scrum_role": "story", "original_parent_id": e2.id}, 3)
    _assign(db, h5, dev_id)
    _make_record(db, p, pm_id, "task", "Endpoint GET /organizations",          "to_do",       10, h5.id, {"scrum_role": "dev"}, 2)
    _make_record(db, p, pm_id, "task", "Componente OrgSelector",               "to_do",       20, h5.id, {"scrum_role": "dev"}, 2)

    h6 = _make_record(db, p, pm_id, "task", "Como PM quiero crear una organizacion",
                      "to_do", 60, s1.id, {"scrum_role": "story", "original_parent_id": e2.id}, 5)
    _assign(db, h6, pm_id)
    _make_record(db, p, pm_id, "task", "Endpoint POST /organizations",         "to_do",       10, h6.id, {"scrum_role": "dev"}, 2)
    _make_record(db, p, pm_id, "task", "Modal de creacion de org",             "to_do",       20, h6.id, {"scrum_role": "dev"}, 2)
    _make_record(db, p, pm_id, "task", "Validacion nombre unico de org",       "backlog",     30, h6.id, {"scrum_role": "dev"}, 1)

    # ── Sprint 2 — pendiente ──────────────────────────────────────────────────
    s2 = _make_record(db, p, pm_id, "sprint", "Sprint 2 - Dashboard & Proyectos", "pendiente", 20,
                      extra={"goal": "Listado de proyectos, acceso a contexto y hub del proyecto"})
    s2.fecha_inicio = date(2026, 6, 23)
    s2.fecha_fin    = date(2026, 7, 6)
    db.flush()

    # ── Historias Sprint 2 (comprometidas) ────────────────────────────────────

    h7 = _make_record(db, p, pm_id, "task", "Como usuario quiero ver mis proyectos",
                      "to_do", 10, s2.id, {"scrum_role": "story", "original_parent_id": e2.id}, 8)
    _assign(db, h7, dev_id, dev2_id)
    _make_record(db, p, pm_id, "task", "Endpoint GET /projects",               "to_do", 10, h7.id, {"scrum_role": "dev"}, 3)
    _make_record(db, p, pm_id, "task", "Componente ProjectListView",           "to_do", 20, h7.id, {"scrum_role": "dev"}, 3)
    _make_record(db, p, pm_id, "task", "Componente ProjectCard v2",            "to_do", 30, h7.id, {"scrum_role": "dev"}, 2)

    h8 = _make_record(db, p, pm_id, "task", "Como PM quiero crear un proyecto",
                      "to_do", 20, s2.id, {"scrum_role": "story", "original_parent_id": e2.id}, 5)
    _assign(db, h8, pm_id, dev_id)
    _make_record(db, p, pm_id, "task", "Endpoint POST /projects",              "to_do", 10, h8.id, {"scrum_role": "dev"}, 2)
    _make_record(db, p, pm_id, "task", "Modal de creacion de proyecto",        "to_do", 20, h8.id, {"scrum_role": "dev"}, 3)
    _make_record(db, p, pm_id, "task", "Selector de pack/template",            "to_do", 30, h8.id, {"scrum_role": "dev"}, 2)

    h9 = _make_record(db, p, pm_id, "task", "Como dev quiero ver el access-context",
                      "to_do", 30, s2.id, {"scrum_role": "story", "original_parent_id": e2.id}, 5)
    _assign(db, h9, dev_id)
    _make_record(db, p, pm_id, "task", "Endpoint GET /projects/{id}/access-context", "to_do", 10, h9.id, {"scrum_role": "dev"}, 5)
    _make_record(db, p, pm_id, "task", "Hook useProjectAccess en FE",          "to_do", 20, h9.id, {"scrum_role": "dev"}, 3)

    # ── Historias en backlog (sin sprint) ────────────────────────────────────

    _make_record(db, p, pm_id, "task", "Como PM quiero ver el overview del proyecto",  "backlog",  10, e2.id, {"scrum_role": "story"}, 8)
    _make_record(db, p, pm_id, "task", "Como dev quiero ver el hub del proyecto",      "backlog",  20, e2.id, {"scrum_role": "story"}, 3)

    _make_record(db, p, pm_id, "task", "Como dev quiero ver el product backlog",       "backlog",  10, e3.id, {"scrum_role": "story"}, 8)
    _make_record(db, p, pm_id, "task", "Como dev quiero ver el sprint board",          "backlog",  20, e3.id, {"scrum_role": "story"}, 5)
    _make_record(db, p, pm_id, "task", "Como dev quiero hacer sprint planning",        "backlog",  30, e3.id, {"scrum_role": "story"}, 5)
    _make_record(db, p, pm_id, "task", "Como dev quiero ver el kanban de dev tasks",   "backlog",  40, e3.id, {"scrum_role": "story"}, 3)
    _make_record(db, p, pm_id, "task", "Como dev quiero ejecutar una Daily standup",   "backlog",  50, e3.id, {"scrum_role": "story"}, 3)

    _make_record(db, p, pm_id, "task", "Como usuario quiero recibir notifs en tiempo real", "backlog", 10, e4.id, {"scrum_role": "story"}, 8)
    _make_record(db, p, pm_id, "task", "Como PM quiero ver el historial de actividad",      "backlog", 20, e4.id, {"scrum_role": "story"}, 5)
    _make_record(db, p, pm_id, "task", "Como usuario quiero ver los cambios de estado",     "backlog", 30, e4.id, {"scrum_role": "story"}, 3)

    print("    + registros scrum creados")


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
    seed_scrum_records(db, scrum_project, pm_id, users)

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
