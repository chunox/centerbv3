import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_actor_id
from app.database import get_db
from app.models.entities import Organization, OrganizationMember, Project, ProjectMember, ProjectRecordBlocker, ProjectRole
from app.schemas.blockers import BlockerResponse
from app.schemas.projects import ProjectResponse
from app.domain.packs.definitions import get_pack, TEMPLATE_TO_PACK

router = APIRouter()


class CreateOrgRequest(BaseModel):
    nombre: str


class OrgResponse(BaseModel):
    id: str
    nombre: str
    slug: str
    estado: str

    model_config = {"from_attributes": True}


def _get_org_or_404(db: Session, org_id: str) -> Organization:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada")
    return org


def _assert_org_member(db: Session, org_id: str, actor_id: str) -> None:
    member = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.organization_id == org_id, OrganizationMember.user_id == actor_id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No pertenecés a esta organización")


@router.post("", response_model=OrgResponse, status_code=status.HTTP_201_CREATED)
def create_organization(
    body: CreateOrgRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """Crea una nueva organización y hace al actor owner."""
    base_slug = re.sub(r"[^a-z0-9]+", "-", body.nombre.lower()).strip("-")
    slug = base_slug
    counter = 1
    while db.query(Organization).filter(Organization.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    org = Organization(nombre=body.nombre, slug=slug)
    db.add(org)
    db.flush()
    member = OrganizationMember(organization_id=org.id, user_id=actor_id, rol="owner")
    db.add(member)
    db.commit()
    db.refresh(org)
    return OrgResponse(id=org.id, nombre=org.nombre, slug=org.slug, estado=org.estado)


@router.get("/{org_id}", response_model=OrgResponse)
def get_organization(
    org_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    org = _get_org_or_404(db, org_id)
    _assert_org_member(db, org_id, actor_id)
    return OrgResponse(id=org.id, nombre=org.nombre, slug=org.slug, estado=org.estado)


@router.get("/{org_id}/blockers", response_model=list[BlockerResponse])
def list_org_blockers(
    org_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """Todos los bloqueantes activos de la org, cross-proyecto."""
    _get_org_or_404(db, org_id)
    _assert_org_member(db, org_id, actor_id)
    projects = (
        db.query(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .filter(
            Project.organization_id == org_id,
            ProjectMember.user_id == actor_id,
        )
        .all()
    )
    project_ids = [p.id for p in projects]
    if not project_ids:
        return []
    blockers = (
        db.query(ProjectRecordBlocker)
        .filter(
            ProjectRecordBlocker.project_id.in_(project_ids),
            ProjectRecordBlocker.resolved_at.is_(None),
        )
        .order_by(ProjectRecordBlocker.created_at)
        .all()
    )
    return [
        BlockerResponse(
            id=b.id, record_id=b.record_id, project_id=b.project_id,
            description=b.description, created_by=b.created_by,
            created_at=b.created_at, resolved_at=b.resolved_at,
            resolved_by=b.resolved_by, resolution_note=b.resolution_note,
            is_resolved=False,
        )
        for b in blockers
    ]


@router.get("/{org_id}/projects", response_model=list[ProjectResponse])
def list_org_projects(
    org_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """
    Lista los proyectos a los que el actor tiene acceso dentro de la org
    (es miembro del proyecto).
    """
    _get_org_or_404(db, org_id)
    _assert_org_member(db, org_id, actor_id)

    projects = (
        db.query(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .filter(
            Project.organization_id == org_id,
            ProjectMember.user_id == actor_id,
            Project.estado != "archivado",
        )
        .order_by(Project.created_at.desc())
        .all()
    )

    return [
        ProjectResponse(
            id=str(p.id),
            org_id=str(p.organization_id),
            name=p.nombre,
            description=p.descripcion,
            pack_slug=p.pack_slug,
            template_slug=p.template_slug,
            delivery_mode=p.delivery_mode,
            estado=p.estado,
            fecha_inicio=p.fecha_inicio,
            fecha_fin=p.fecha_fin,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in projects
    ]


class CreateProjectRequest(BaseModel):
    nombre: str
    pack_slug: str
    template_slug: str
    delivery_mode: str
    descripcion: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None


@router.post("/{org_id}/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    org_id: str,
    body: CreateProjectRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """Crea un proyecto, registra roles del pack y hace al actor PM."""
    org = _get_org_or_404(db, org_id)
    _assert_org_member(db, org_id, actor_id)

    today = date.today()
    project = Project(
        organization_id=org.id,
        nombre=body.nombre,
        descripcion=body.descripcion,
        pack_slug=body.pack_slug,
        template_slug=body.template_slug,
        delivery_mode=body.delivery_mode,
        estado="activo",
        fecha_inicio=body.fecha_inicio or today,
        fecha_fin=body.fecha_fin or today,
        settings={},
        created_by=actor_id,
    )
    db.add(project)
    db.flush()

    # Crear roles definidos en el pack
    pack_key = TEMPLATE_TO_PACK.get(body.template_slug, body.pack_slug)
    pack = get_pack(pack_key)
    roles_map: dict[str, ProjectRole] = {}
    if pack:
        for role_slug, role_name in pack.roles.items():
            role = ProjectRole(project_id=project.id, slug=role_slug, nombre=role_name)
            db.add(role)
            db.flush()
            roles_map[role_slug] = role

    # Actor como PM
    pm_role = roles_map.get("pm")
    if pm_role:
        db.add(ProjectMember(project_id=project.id, user_id=actor_id, role_id=pm_role.id))

    db.commit()
    db.refresh(project)

    return ProjectResponse(
        id=project.id, org_id=project.organization_id, name=project.nombre,
        description=project.descripcion, pack_slug=project.pack_slug,
        template_slug=project.template_slug, delivery_mode=project.delivery_mode,
        estado=project.estado, fecha_inicio=project.fecha_inicio,
        fecha_fin=project.fecha_fin, created_at=project.created_at, updated_at=project.updated_at,
    )
