"""
seed_demo.py — Crea datos demo para desarrollo local.

Proyectos:
  - Software Demo (waterfall, pack=software-waterfall, template=t3_interno_clasico)
  - Scrum Demo    (scrum,     pack=software-scrum,     template=t6_scrum_interno)

Uso:
    cd proyecto-central-backend-v3
    python scripts/seed_demo.py
    python scripts/seed_demo.py --reset
"""
import argparse
import sys
import os
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_engine, get_session_factory
from app.models.entities import (
    Base, Organization, OrganizationMember, Project, ProjectMember, ProjectRecord,
    ProjectRecordAssignee, ProjectRecordBlocker, ProjectRole, User,
    ScrumCeremonySession, ScrumCeremonyEntry, HubEntry,
)
from app.services.auth_service import hash_password


# ─── Datos constantes ────────────────────────────────────────────────────────

DEMO_USERS = [
    {"nombre": "PM Demo",      "email": "pm@center.demo",      "password": "demo12345"},
    {"nombre": "TL Demo",      "email": "tl@center.demo",      "password": "demo12345"},
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
    "tl@center.demo":      "tech_lead",
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
    f2 = _make_record(db, p, pm_id, "feature",   "Dashboard de proyectos",       "in_review",   20, m1.id)
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


def _dev(
    db,
    project_id: str,
    actor_id: str,
    parent_id: str,
    title: str,
    status: str,
    orden: int,
    estimacion: float | None = None,
    assignees: tuple = (),
) -> ProjectRecord:
    task = _make_record(
        db, project_id, actor_id, "task", title, status, orden, parent_id,
        {"scrum_role": "dev"}, estimacion,
    )
    if assignees:
        _assign(db, task, *assignees)
    return task


def _sub(
    db,
    project_id: str,
    actor_id: str,
    parent_id: str,
    title: str,
    status: str,
    orden: int,
    estimacion: float | None = None,
    assignees: tuple = (),
) -> ProjectRecord:
    task = _make_record(
        db, project_id, actor_id, "task", title, status, orden, parent_id,
        {"scrum_role": "subtask"}, estimacion,
    )
    if assignees:
        _assign(db, task, *assignees)
    return task


def _story_in_sprint(
    db,
    project_id: str,
    actor_id: str,
    sprint_id: str,
    epic_id: str,
    title: str,
    status: str,
    orden: int,
    estimacion: float | None = None,
    assignees: tuple = (),
) -> ProjectRecord:
    story = _make_record(
        db, project_id, actor_id, "task", title, status, orden, sprint_id,
        {"scrum_role": "story", "original_parent_id": epic_id}, estimacion,
    )
    if assignees:
        _assign(db, story, *assignees)
    return story


def _find_record(db, project_id: str, title: str) -> ProjectRecord | None:
    return db.query(ProjectRecord).filter(
        ProjectRecord.project_id == project_id,
        ProjectRecord.title == title,
    ).first()


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

    # ── Épicas adicionales ────────────────────────────────────────────────────
    e5 = _make_record(db, p, pm_id, "task", "Integraciones y API publica",  "backlog", 50, backlog.id, {"scrum_role": "epic"}, 32)
    e6 = _make_record(db, p, pm_id, "task", "Calidad y observabilidad",   "backlog", 60, backlog.id, {"scrum_role": "epic"}, 24)

    # ── Subtareas en dev tasks existentes ─────────────────────────────────────
    for title, subs in (
        ("Endpoint POST /auth/register", (
            ("Tests unitarios endpoint register", "done", 10, 1),
            ("Documentar contrato OpenAPI", "done", 20, 1),
        )),
        ("Endpoint POST /auth/login", (
            ("Rate limiting por IP", "done", 10, 1),
            ("Logs de intentos fallidos", "done", 20, 0.5),
        )),
        ("Endpoint POST /auth/forgot-password", (
            ("Template email HTML", "done", 10, 1),
            ("Token expira en 1h", "done", 20, 0.5),
        )),
        ("Pantalla de perfil con avatar", (
            ("Formulario edicion nombre", "in_progress", 10, 1),
            ("Validacion email unico", "to_do", 20, 1),
        )),
        ("Endpoint GET /projects", (
            ("Paginacion cursor-based", "to_do", 10, 1),
            ("Filtros por pack y estado", "to_do", 20, 1.5),
        )),
        ("Endpoint GET /projects/{id}/access-context", (
            ("Cache ETag 60s", "to_do", 10, 1),
            ("Tests contrato access-context", "to_do", 20, 1),
        )),
    ):
        parent = _find_record(db, p, title)
        if parent:
            for sub_title, sub_status, sub_orden, sub_hours in subs:
                assignee = (dev2_id,) if "email" in sub_title or "SMTP" in sub_title else (dev_id,)
                _sub(db, p, pm_id, parent.id, sub_title, sub_status, sub_orden, sub_hours, assignee)

    if t_alembic:
        _sub(db, p, pm_id, t_alembic.id, "Revision autogenerate script", "done", 30, 0.5, (dev2_id,))
        _sub(db, p, pm_id, t_alembic.id, "Seed idempotente demo", "done", 40, 1, (dev_id,))

    # ── Historia y dev tasks adicionales en Sprint 1 ──────────────────────────
    h13 = _story_in_sprint(
        db, p, pm_id, s1.id, e2.id,
        "Como usuario quiero cambiar mi password", "to_do", 70, 3, (dev_id,),
    )
    t_chg_pwd = _dev(db, p, pm_id, h13.id, "Endpoint PATCH /users/me/password", "to_do", 10, 2, (dev_id,))
    _sub(db, p, pm_id, t_chg_pwd.id, "Validacion password actual", "to_do", 10, 0.5, (dev_id,))
    _sub(db, p, pm_id, t_chg_pwd.id, "Pantalla cambio password", "to_do", 20, 1.5, (dev_id,))

    h14 = _story_in_sprint(
        db, p, pm_id, s1.id, e1.id,
        "Como usuario quiero cerrar sesion en todos los dispositivos", "to_do", 80, 5, (dev_id,),
    )
    t_logout = _dev(db, p, pm_id, h14.id, "Endpoint POST /auth/logout-all", "to_do", 10, 2, (dev_id,))
    _dev(db, p, pm_id, h14.id, "Boton cerrar sesion global en perfil", "to_do", 20, 2, (dev2_id,))
    _sub(db, p, pm_id, t_logout.id, "Invalidar refresh tokens en BD", "to_do", 10, 1, (dev_id,))
    _sub(db, p, pm_id, t_logout.id, "Notificar sesiones activas por email", "to_do", 20, 1, (dev2_id,))

    # ── Sprint 3 — pendiente ──────────────────────────────────────────────────
    s3 = _make_record(db, p, pm_id, "sprint", "Sprint 3 - Integraciones", "pendiente", 30,
                      extra={"goal": "Webhooks, API keys y exportacion de datos"})
    s3.fecha_inicio = date(2026, 7, 7)
    s3.fecha_fin    = date(2026, 7, 20)
    db.flush()

    h15 = _story_in_sprint(
        db, p, pm_id, s3.id, e5.id,
        "Como dev quiero consumir webhooks de eventos", "to_do", 10, 8, (dev_id,),
    )
    t_webhook = _dev(db, p, pm_id, h15.id, "Endpoint CRUD /webhooks", "to_do", 10, 3, (dev_id,))
    _sub(db, p, pm_id, t_webhook.id, "Modelo WebhookSubscription", "to_do", 10, 1, (dev_id,))
    _sub(db, p, pm_id, t_webhook.id, "Firma HMAC de payloads", "to_do", 20, 2, (dev_id,))
    _sub(db, p, pm_id, t_webhook.id, "Retry con backoff exponencial", "to_do", 30, 1.5, (dev2_id,))

    h16 = _story_in_sprint(
        db, p, pm_id, s3.id, e5.id,
        "Como PM quiero generar API keys", "to_do", 20, 5, (pm_id, dev_id),
    )
    t_apikey = _dev(db, p, pm_id, h16.id, "Endpoint POST /api-keys", "to_do", 10, 2, (dev_id,))
    t_revoke = _dev(db, p, pm_id, h16.id, "Revocacion y rotacion de keys", "to_do", 20, 2, (dev2_id,))
    _sub(db, p, pm_id, t_apikey.id, "Hash bcrypt de secret", "to_do", 10, 0.5, (dev_id,))
    _sub(db, p, pm_id, t_apikey.id, "UI modal generar key", "to_do", 20, 1.5, (dev_id,))
    _sub(db, p, pm_id, t_revoke.id, "Audit log de revocacion", "to_do", 10, 1, (dev2_id,))

    h17 = _story_in_sprint(
        db, p, pm_id, s3.id, e6.id,
        "Como PM quiero exportar registros a CSV", "to_do", 30, 5, (pm_id,),
    )
    t_export = _dev(db, p, pm_id, h17.id, "Servicio export CSV async", "to_do", 10, 3, (dev2_id,))
    _dev(db, p, pm_id, h17.id, "Boton export en listados", "to_do", 20, 2, (dev_id,))
    _sub(db, p, pm_id, t_export.id, "Streaming de filas grandes", "to_do", 10, 1.5, (dev2_id,))
    _sub(db, p, pm_id, t_export.id, "Job en cola + notificacion", "to_do", 20, 1.5, (dev2_id,))

    # ── Historias adicionales en Sprint 2 ─────────────────────────────────────
    h18 = _story_in_sprint(
        db, p, pm_id, s2.id, e2.id,
        "Como PM quiero invitar miembros al proyecto", "to_do", 40, 5, (pm_id,),
    )
    t_invite = _dev(db, p, pm_id, h18.id, "Endpoint POST /projects/{id}/members", "to_do", 10, 2, (dev_id,))
    _dev(db, p, pm_id, h18.id, "Modal invitar por email", "to_do", 20, 2, (dev2_id,))
    _sub(db, p, pm_id, t_invite.id, "Email de invitacion con token", "to_do", 10, 1, (dev_id,))
    _sub(db, p, pm_id, t_invite.id, "Asignacion de rol al aceptar", "to_do", 20, 1, (dev_id,))

    # ── Backlog adicional ─────────────────────────────────────────────────────
    _make_record(db, p, pm_id, "task", "Como dev quiero filtrar el backlog por epica",       "backlog", 60, e3.id, {"scrum_role": "story"}, 3)
    _make_record(db, p, pm_id, "task", "Como dev quiero crear subtareas desde el kanban",    "backlog", 70, e3.id, {"scrum_role": "story"}, 2)
    _make_record(db, p, pm_id, "task", "Como PM quiero configurar unidades de esfuerzo",      "backlog", 80, e3.id, {"scrum_role": "story"}, 2)
    _make_record(db, p, pm_id, "task", "Como dev quiero integrar con Slack",                 "backlog", 10, e5.id, {"scrum_role": "story"}, 13)
    _make_record(db, p, pm_id, "task", "Como PM quiero metricas de velocidad del equipo",    "backlog", 10, e6.id, {"scrum_role": "story"}, 8)
    _make_record(db, p, pm_id, "task", "Como dev quiero tracing OpenTelemetry",              "backlog", 20, e6.id, {"scrum_role": "story"}, 5)
    _make_record(db, p, pm_id, "task", "Como QA quiero reportes de cobertura por sprint",    "backlog", 30, e6.id, {"scrum_role": "story"}, 5)

    print("    + registros scrum creados")


def _make_blocker(
    db,
    project_id: str,
    record_id: str,
    created_by: str,
    description: str,
    *,
    resolved: bool = False,
    resolved_by: str | None = None,
) -> ProjectRecordBlocker | None:
    existing = db.query(ProjectRecordBlocker).filter(
        ProjectRecordBlocker.project_id == project_id,
        ProjectRecordBlocker.record_id == record_id,
        ProjectRecordBlocker.description == description,
    ).first()
    if existing:
        return existing
    now = datetime.now(timezone.utc)
    blocker = ProjectRecordBlocker(
        project_id=project_id,
        record_id=record_id,
        description=description,
        created_by=created_by,
        resolved_at=now if resolved else None,
        resolved_by=resolved_by if resolved else None,
        resolution_note="Resuelto en demo" if resolved else None,
    )
    db.add(blocker)
    db.flush()
    return blocker


def seed_waterfall_extras(db, project: Project, pm_id: str):
    """Bloqueante activo en feature Dashboard + bloqueante resuelto en Login."""
    p = project.id
    f_dashboard = _find_record(db, p, "Dashboard de proyectos")
    f_login = _find_record(db, p, "Autenticacion de usuarios")
    if f_dashboard:
        _make_blocker(
            db, p, f_dashboard.id, pm_id,
            "**Bloqueo activo:** pendiente definición de permisos por rol en Settings.",
        )
    if f_login:
        _make_blocker(
            db, p, f_login.id, pm_id,
            "Dependencia de proveedor OAuth externo (resuelto).",
            resolved=True,
            resolved_by=pm_id,
        )
    print("    + bloqueantes waterfall")


def seed_scrum_extras(db, project: Project, pm_id: str, users: dict):
    """Bloqueante activo en historia de password recovery."""
    p = project.id
    h3 = _find_record(db, p, "Como usuario quiero recuperar mi password")
    if h3:
        _make_blocker(
            db, p, h3.id, users["tl@center.demo"].id,
            "**Bloqueo activo:** servicio SMTP no configurado en staging.",
        )
    print("    + bloqueantes scrum")


def seed_hub_entries(db, project: Project, author_id: str):
    p = project.id
    entries = [
        ("decision", "Stack MVP1", "Backend FastAPI + SQLAlchemy. Frontend React 19 + Vite 6."),
        ("nota", "Convención de estados", "Work items en inglés (`backlog`, `in_progress`, `done`). Sprint/ceremonias en español."),
        ("riesgo", "Email en dev", "Reset de password loguea el link en consola hasta configurar SMTP."),
    ]
    for tipo, titulo, contenido in entries:
        exists = db.query(HubEntry).filter(
            HubEntry.project_id == p,
            HubEntry.titulo == titulo,
        ).first()
        if not exists:
            db.add(HubEntry(
                project_id=p,
                author_id=author_id,
                tipo=tipo,
                titulo=titulo,
                contenido=contenido,
            ))
    db.flush()
    print("    + hub entries")


def seed_ceremony_sessions(db, project: Project, pm_id: str, users: dict):
    """Daily cerrada del sprint activo + planning pendiente."""
    p = project.id
    s1 = _find_record(db, p, "Sprint 1 - Auth & Registro")
    if not s1:
        return

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    daily = db.query(ScrumCeremonySession).filter(
        ScrumCeremonySession.project_id == p,
        ScrumCeremonySession.session_type == "daily",
        ScrumCeremonySession.sprint_id == s1.id,
    ).first()
    if not daily:
        daily = ScrumCeremonySession(
            project_id=p,
            sprint_id=s1.id,
            session_type="daily",
            status="cerrada",
            started_at=yesterday.replace(hour=14, minute=0),
            closed_at=yesterday.replace(hour=14, minute=25),
            created_by=pm_id,
        )
        db.add(daily)
        db.flush()

        standups = [
            (users["dev@center.demo"].id, "Cerré login y registro.", "Password recovery + perfil.", []),
            (users["dev2@center.demo"].id, "Avancé pantalla reset.", "Integrar envío SMTP.", ["blocker-smtp"]),
            (users["qa@center.demo"].id, "Casos de prueba auth listos.", "Probar flujo reset E2E.", []),
        ]
        for author_id, ayer, hoy, bloqueantes in standups:
            exists = db.query(ScrumCeremonyEntry).filter(
                ScrumCeremonyEntry.session_id == daily.id,
                ScrumCeremonyEntry.author_id == author_id,
                ScrumCeremonyEntry.entry_type == "standup",
            ).first()
            if not exists:
                db.add(ScrumCeremonyEntry(
                    session_id=daily.id,
                    author_id=author_id,
                    entry_type="standup",
                    payload={"ayer": ayer, "hoy": hoy, "bloqueantes": bloqueantes},
                ))

    planning = db.query(ScrumCeremonySession).filter(
        ScrumCeremonySession.project_id == p,
        ScrumCeremonySession.session_type == "planning",
        ScrumCeremonySession.status == "pendiente",
    ).first()
    if not planning:
        db.add(ScrumCeremonySession(
            project_id=p,
            sprint_id=s1.id,
            session_type="planning",
            status="pendiente",
            created_by=pm_id,
        ))

    print("    + ceremonias (daily cerrada + planning pendiente)")


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
    seed_waterfall_extras(db, wf_project, pm_id)
    seed_hub_entries(db, wf_project, pm_id)

    print("\n== Proyecto Scrum ==")
    scrum_project, _ = seed_project(
        db, org, users,
        nombre="Scrum Demo",
        pack_slug="software-scrum",
        template_slug="t6_scrum_interno",
        delivery_mode="scrum",
    )
    seed_scrum_records(db, scrum_project, pm_id, users)
    seed_scrum_extras(db, scrum_project, pm_id, users)
    seed_hub_entries(db, scrum_project, pm_id)
    seed_ceremony_sessions(db, scrum_project, pm_id, users)

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
