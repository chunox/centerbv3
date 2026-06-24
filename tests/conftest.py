"""
Fixtures globales de pytest para Center MVP1.
DB: SQLite en memoria (no toca el archivo de dev).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    Organization, OrganizationMember,
    Project, ProjectRole, ProjectMember,
    User,
)
from app.services.auth_service import hash_password, create_access_token
from app.domain.packs.definitions import WATERFALL_PACK, SCRUM_PACK

# ─── Motor SQLite en memoria ──────────────────────────────────────────────────

TEST_DB_URL = "sqlite:///:memory:"

engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Crea todas las tablas antes de la sesión de tests."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db() -> Session:
    """DB session aislada por test con rollback al finalizar."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db: Session) -> TestClient:
    """TestClient con la DB de test inyectada."""
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ─── Factories ────────────────────────────────────────────────────────────────

def make_user(
    db: Session,
    email: str = "test@center.demo",
    nombre: str = "Test User",
    password: str = "testpass123",
) -> User:
    user = User(email=email, nombre=nombre, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    return user


def make_org(db: Session, owner: User, nombre: str = "Test Org") -> Organization:
    slug = nombre.lower().replace(" ", "-")
    org = Organization(nombre=nombre, slug=slug)
    db.add(org)
    db.flush()
    member = OrganizationMember(organization_id=org.id, user_id=owner.id, rol="owner")
    db.add(member)
    db.flush()
    return org


def make_project(
    db: Session,
    org: Organization,
    creator: User,
    pack_slug: str = "software-waterfall",
    template_slug: str = "t3_interno_clasico",
    delivery_mode: str = "waterfall",
    nombre: str = "Test Project",
) -> Project:
    from datetime import date
    project = Project(
        organization_id=org.id,
        nombre=nombre,
        pack_slug=pack_slug,
        template_slug=template_slug,
        delivery_mode=delivery_mode,
        fecha_inicio=date.today(),
        fecha_fin=date.today(),
        settings={"effort_unit": "hours", "hours_per_story_point": 6},
        created_by=creator.id,
    )
    db.add(project)
    db.flush()
    return project


def make_project_role(
    db: Session,
    project: Project,
    slug: str = "pm",
    nombre: str = "PM",
) -> ProjectRole:
    role = ProjectRole(project_id=project.id, slug=slug, nombre=nombre)
    db.add(role)
    db.flush()
    return role


def make_member(
    db: Session,
    project: Project,
    user: User,
    role: ProjectRole,
) -> ProjectMember:
    member = ProjectMember(project_id=project.id, user_id=user.id, role_id=role.id)
    db.add(member)
    db.flush()
    return member


def auth_headers(user: User) -> dict[str, str]:
    """Genera headers JWT para un usuario."""
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


# ─── Fixture compuesto: proyecto con PM ──────────────────────────────────────

@pytest.fixture()
def project_with_pm(db: Session):
    """
    Devuelve (user, org, project, role, member, headers).
    Usuario pm@test.demo como PM del proyecto de prueba.
    """
    user = make_user(db, email="pm@test.demo", nombre="PM Test")
    org = make_org(db, user)
    project = make_project(db, org, user)
    role = make_project_role(db, project, slug="pm", nombre="PM")
    member = make_member(db, project, user, role)
    db.commit()
    return {
        "user": user,
        "org": org,
        "project": project,
        "role": role,
        "member": member,
        "headers": auth_headers(user),
    }
