"""
Modelos SQLAlchemy — schema v8 (organizaciones + dominio PM).

Relaciones principales:
  User ↔ OrganizationMember ↔ Organization
  Organization → Project → ProjectRecord (generic)
  ProjectMember: rol por proyecto (pm/dev/qa/cliente), independiente de org
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    projects_created: Mapped[list[Project]] = relationship(back_populates="creator")
    project_memberships: Mapped[list[ProjectMember]] = relationship(
        back_populates="user"
    )
    comments: Mapped[list[Comment]] = relationship(back_populates="author")
    documents_created: Mapped[list[Document]] = relationship(
        back_populates="creator"
    )
    hub_entries_authored: Mapped[list[HubEntry]] = relationship(
        back_populates="author"
    )
    document_exposures_created: Mapped[list[DocumentExposure]] = relationship(
        back_populates="exposer"
    )
    attachments_uploaded: Mapped[list[Attachment]] = relationship(
        back_populates="uploader"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="user")
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    organization_memberships: Mapped[list[OrganizationMember]] = relationship(
        back_populates="user"
    )
    organization_invites_created: Mapped[list[OrganizationInvite]] = relationship(
        back_populates="creator"
    )
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


# ── SaaS: organización como tenant superior a proyectos ──────────────────

class Organization(Base):
    """Espacio de trabajo del equipo (multi-org por usuario)."""
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('activa', 'suspendida')", name="chk_organizations_estado"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="activa")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    members: Mapped[list[OrganizationMember]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    invites: Mapped[list[OrganizationInvite]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    projects: Mapped[list[Project]] = relationship(back_populates="organization")


class OrganizationMember(Base):
    """Membresía org: owner/admin ven todos los proyectos; member necesita project_member."""
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_organization_member"),
        CheckConstraint(
            "rol IN ('owner', 'admin', 'member')", name="chk_organization_member_rol"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rol: Mapped[str] = mapped_column(String(20), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="organization_memberships")


class OrganizationInvite(Base):
    __tablename__ = "organization_invites"
    __table_args__ = (
        CheckConstraint(
            "rol IN ('admin', 'member')", name="chk_organization_invite_rol"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    organization: Mapped[Organization] = relationship(back_populates="invites")
    creator: Mapped[User] = relationship(back_populates="organization_invites_created")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    user: Mapped[User] = relationship(back_populates="password_reset_tokens")


class Project(Base):
    """Proyecto acotado a una organization_id (obligatorio desde schema v8)."""
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("fecha_fin >= fecha_inicio", name="chk_project_fechas"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_slug: Mapped[str] = mapped_column(
        String(40), nullable=False, default="default"
    )
    template_slug: Mapped[str] = mapped_column(
        String(40), nullable=False, default="t1_cliente_clasico"
    )
    pack_slug: Mapped[str] = mapped_column(
        String(40), nullable=False, default="software"
    )
    structure_version: Mapped[int] = mapped_column(nullable=False, default=2)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="activo")
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    organization: Mapped[Organization] = relationship(back_populates="projects")
    creator: Mapped[User] = relationship(back_populates="projects_created")
    members: Mapped[list[ProjectMember]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    document: Mapped[Document | None] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="project")
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    document_exposures: Mapped[list[DocumentExposure]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    hub_entries: Mapped[list[HubEntry]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    roles: Mapped[list["ProjectRole"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    workflow_definitions: Mapped[list["ProjectWorkflowDefinition"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    workbench_definition: Mapped["ProjectWorkbenchDefinition | None"] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    communication_rules: Mapped["ProjectCommunicationRules | None"] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    record_types: Mapped[list["ProjectRecordType"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    records: Mapped[list["ProjectRecord"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    blocks: Mapped[list["ProjectBlock"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    views: Mapped[list["ProjectView"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    field_definitions: Mapped[list["ProjectFieldDefinition"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class BlockCatalog(Base):
    """Catálogo global de bloques reutilizables (kanban, inbox, gantt, etc.)."""
    __tablename__ = "block_catalog"

    slug: Mapped[str] = mapped_column(String(40), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProjectBlock(Base):
    """Instancia de bloque activa en un proyecto."""
    __tablename__ = "project_blocks"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_project_block_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    block_slug: Mapped[str] = mapped_column(
        String(40), ForeignKey("block_catalog.slug"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="blocks")


class ProjectView(Base):
    """Vista de navegación que compone uno o más bloques."""
    __tablename__ = "project_views"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_project_view_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    route: Mapped[str] = mapped_column(String(80), nullable=False)
    icon: Mapped[str] = mapped_column(String(40), nullable=False, default="circle")
    section: Mapped[str] = mapped_column(String(20), nullable=False, default="plan")
    layout: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    required_capabilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="views")


class ProjectFieldDefinition(Base):
    """Definición de campo personalizado por entity type en un proyecto."""
    __tablename__ = "project_field_definitions"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "entity_type_key", "field_key", name="uq_project_field_def"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    entity_type_key: Mapped[str] = mapped_column(String(40), nullable=False)
    field_key: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="field_definitions")


class ProjectPack(Base):
    """Catálogo global de packs de proyecto."""
    __tablename__ = "project_packs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest: Mapped[str] = mapped_column(Text, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ProjectRecordType(Base):
    """Tipo de entidad activo en un proyecto (copiado del pack)."""
    __tablename__ = "project_record_types"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_project_record_type_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    storage: Mapped[str] = mapped_column(String(10), nullable=False, default="generic")
    field_schema: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    parent_types: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(40), nullable=True)
    traits: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="record_types")


class ProjectRecord(Base):
    """Registro genérico de proyecto."""
    __tablename__ = "project_records"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    record_type: Mapped[str] = mapped_column(String(40), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("project_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(String(40), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fecha_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    project: Mapped[Project] = relationship(back_populates="records")
    parent: Mapped["ProjectRecord | None"] = relationship(
        remote_side="ProjectRecord.id", back_populates="children"
    )
    children: Mapped[list["ProjectRecord"]] = relationship(back_populates="parent")
    assignees: Mapped[list["ProjectRecordAssignee"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )


class ProjectRecordAssignee(Base):
    __tablename__ = "project_record_assignees"

    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("project_records.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )

    record: Mapped[ProjectRecord] = relationship(back_populates="assignees")
    user: Mapped[User] = relationship()


class ProjectRecordDependency(Base):
    __tablename__ = "project_record_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "predecessor_id", "successor_id", name="uq_record_dependency_pair"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    predecessor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("project_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    successor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("project_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    dependency_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="finish_to_start"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ProjectRole(Base):
    """Rol configurable por proyecto (sistema o custom)."""
    __tablename__ = "project_roles"
    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_project_role_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="roles")
    capabilities: Mapped[list["ProjectRoleCapability"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )
    members: Mapped[list["ProjectMember"]] = relationship(back_populates="role")


class ProjectRoleCapability(Base):
    __tablename__ = "project_role_capabilities"
    __table_args__ = (
        UniqueConstraint("role_id", "capability_key", name="uq_role_capability"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_roles.id", ondelete="CASCADE"), nullable=False
    )
    capability_key: Mapped[str] = mapped_column(String(80), nullable=False)

    role: Mapped[ProjectRole] = relationship(back_populates="capabilities")


class ProjectWorkflowDefinition(Base):
    """Workflow versionado por tipo de entidad y proyecto."""
    __tablename__ = "project_workflow_definitions"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "entity_type", "version", name="uq_project_workflow_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="workflow_definitions")


class ProjectWorkbenchDefinition(Base):
    """Workbenches (sidebar) configurables por proyecto."""
    __tablename__ = "project_workbench_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    project: Mapped[Project] = relationship(back_populates="workbench_definition")


class ProjectCommunicationRules(Base):
    """Reglas de comunicación configurables por proyecto (Studio)."""
    __tablename__ = "project_communication_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    definition: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    project: Mapped[Project] = relationship(back_populates="communication_rules")


class ProjectConfigSnapshot(Base):
    """Snapshots de configuración Studio (workflows, communication, workbenches)."""
    __tablename__ = "project_config_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ProjectMember(Base):
    """Acceso por proyecto; un cliente puede ser member sin OrganizationMember (guest)."""
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", "role_id", name="uq_project_member"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_roles.id", ondelete="CASCADE"), nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="project_memberships")
    role: Mapped[ProjectRole] = relationship(back_populates="members")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entidad_tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    entidad_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    estado_momento: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    author: Mapped[User] = relationship(back_populates="comments")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    contenido: Mapped[str | None] = mapped_column(Text, nullable=True)
    archivo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    visibilidad: Mapped[str] = mapped_column(String(10), nullable=False, default="publico")
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    project: Mapped[Project] = relationship(back_populates="document")
    creator: Mapped[User] = relationship(back_populates="documents_created")
    exposures: Mapped[list[DocumentExposure]] = relationship(
        back_populates="document"
    )


class HubEntry(Base):
    __tablename__ = "hub_entries"
    __table_args__ = (
        CheckConstraint("tipo IN ('update', 'note')", name="chk_hub_entry_tipo"),
        CheckConstraint(
            "visibilidad IN ('publico', 'interno')", name="chk_hub_entry_visibilidad"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)
    titulo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    visibilidad: Mapped[str] = mapped_column(String(10), nullable=False, default="publico")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    project: Mapped[Project] = relationship(back_populates="hub_entries")
    author: Mapped[User] = relationship(back_populates="hub_entries_authored")
    exposures: Mapped[list[DocumentExposure]] = relationship(back_populates="hub_entry")


class DocumentExposure(Base):
    __tablename__ = "document_exposures"
    __table_args__ = (
        CheckConstraint(
            "(document_id IS NOT NULL AND attachment_id IS NULL AND hub_entry_id IS NULL) "
            "OR (document_id IS NULL AND attachment_id IS NOT NULL AND hub_entry_id IS NULL) "
            "OR (document_id IS NULL AND attachment_id IS NULL AND hub_entry_id IS NOT NULL)",
            name="chk_exposure_target",
        ),
        CheckConstraint(
            "(ambito = 'proyecto' AND milestone_id IS NULL AND feature_id IS NULL) "
            "OR (ambito = 'milestone' AND milestone_id IS NOT NULL "
            "AND feature_id IS NULL) "
            "OR (ambito = 'feature' AND feature_id IS NOT NULL)",
            name="chk_exposure_ambito",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    ambito: Mapped[str] = mapped_column(String(20), nullable=False)
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("project_records.id", ondelete="CASCADE"),
        nullable=True,
    )
    feature_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("project_records.id", ondelete="CASCADE"),
        nullable=True,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
    )
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("attachments.id", ondelete="CASCADE"),
        nullable=True,
    )
    hub_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("hub_entries.id", ondelete="CASCADE"),
        nullable=True,
    )
    titulo_visible: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expuesto_por: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="document_exposures")
    milestone: Mapped["ProjectRecord | None"] = relationship(
        foreign_keys=[milestone_id]
    )
    feature: Mapped["ProjectRecord | None"] = relationship(foreign_keys=[feature_id])
    document: Mapped[Document | None] = relationship(back_populates="exposures")
    attachment: Mapped[Attachment | None] = relationship(
        back_populates="exposures"
    )
    hub_entry: Mapped[HubEntry | None] = relationship(back_populates="exposures")
    exposer: Mapped[User] = relationship(back_populates="document_exposures_created")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    nombre_original: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    uploader: Mapped[User] = relationship(back_populates="attachments_uploaded")
    relations: Mapped[list[AttachmentRelation]] = relationship(
        back_populates="attachment", cascade="all, delete-orphan"
    )
    exposures: Mapped[list[DocumentExposure]] = relationship(
        back_populates="attachment"
    )


class AttachmentRelation(Base):
    __tablename__ = "attachment_relations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    attachment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("attachments.id", ondelete="CASCADE"),
        nullable=False,
    )
    entidad_tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    entidad_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    attachment: Mapped[Attachment] = relationship(back_populates="relations")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    entidad_tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    entidad_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    accion: Mapped[str] = mapped_column(String(30), nullable=False)
    campo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    valor_anterior: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_nuevo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="audit_logs")
    user: Mapped[User] = relationship(back_populates="audit_logs")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    entidad_tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    entidad_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    leida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deep_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    user: Mapped[User] = relationship(back_populates="notifications")
    project: Mapped[Project] = relationship(back_populates="notifications")

