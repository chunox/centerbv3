"""
Modelos SQLAlchemy — schema v8 (organizaciones + dominio PM).

Relaciones principales:
  User ↔ OrganizationMember ↔ Organization
  Organization → Project → Milestone → Feature → Task
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
    milestones_created: Mapped[list[Milestone]] = relationship(
        back_populates="creator"
    )
    features_created: Mapped[list[Feature]] = relationship(back_populates="creator")
    tasks_assigned: Mapped[list[Task]] = relationship(
        back_populates="assignee", foreign_keys="Task.asignado_a"
    )
    tasks_created: Mapped[list[Task]] = relationship(
        back_populates="creator", foreign_keys="Task.created_by"
    )
    feature_reports_submitted: Mapped[list[FeatureReport]] = relationship(
        back_populates="reporter", foreign_keys="FeatureReport.reported_by"
    )
    feature_queries_created: Mapped[list[FeatureQuery]] = relationship(
        back_populates="creator", foreign_keys="FeatureQuery.created_by"
    )
    comments: Mapped[list[Comment]] = relationship(back_populates="author")
    documents_created: Mapped[list[Document]] = relationship(
        back_populates="creator"
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
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, default="con_cliente")
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
    milestones: Mapped[list[Milestone]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    features: Mapped[list[Feature]] = relationship(back_populates="project")
    tasks: Mapped[list[Task]] = relationship(back_populates="project")
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


class ProjectMember(Base):
    """Acceso por proyecto; un cliente puede ser member sin OrganizationMember (guest)."""
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", "rol", name="uq_project_member"),
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
    rol: Mapped[str] = mapped_column(String(20), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="project_memberships")


class Milestone(Base):
    __tablename__ = "milestones"
    __table_args__ = (
        CheckConstraint("fecha_fin >= fecha_inicio", name="chk_milestone_fechas"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, default="entrega")
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(String(25), nullable=False, default="pendiente")
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    project: Mapped[Project] = relationship(back_populates="milestones")
    creator: Mapped[User] = relationship(back_populates="milestones_created")
    features: Mapped[list[Feature]] = relationship(
        back_populates="milestone", cascade="all, delete-orphan"
    )


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (
        CheckConstraint("fecha_fin >= fecha_inicio", name="chk_feature_fechas"),
        CheckConstraint(
            "tipo <> 'mejora' OR duracion_estimada IS NOT NULL",
            name="chk_feature_duracion_mejora",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    milestone_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("milestones.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, default="desarrollo")
    prioridad: Mapped[str] = mapped_column(String(10), nullable=False, default="media")
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    duracion_estimada: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[str] = mapped_column(String(40), nullable=False, default="pendiente")
    bloqueada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    origen_report_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("feature_reports.id"), nullable=True
    )
    origen_feature_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("features.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    milestone: Mapped[Milestone] = relationship(back_populates="features")
    project: Mapped[Project] = relationship(back_populates="features")
    creator: Mapped[User] = relationship(back_populates="features_created")
    tasks: Mapped[list[Task]] = relationship(
        back_populates="feature", cascade="all, delete-orphan"
    )
    reports: Mapped[list[FeatureReport]] = relationship(
        back_populates="feature",
        foreign_keys="FeatureReport.feature_id",
        cascade="all, delete-orphan",
    )
    origen_report: Mapped[FeatureReport | None] = relationship(
        foreign_keys=[origen_report_id],
    )
    origen_feature: Mapped[Feature | None] = relationship(
        foreign_keys=[origen_feature_id],
        remote_side="Feature.id",
    )
    queries: Mapped[list[FeatureQuery]] = relationship(
        back_populates="feature", cascade="all, delete-orphan"
    )


class FeatureReport(Base):
    __tablename__ = "feature_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    feature_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("features.id", ondelete="CASCADE"),
        nullable=False,
    )
    reported_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    generated_feature_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("features.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    feature: Mapped[Feature] = relationship(
        back_populates="reports", foreign_keys=[feature_id]
    )
    reporter: Mapped[User] = relationship(
        back_populates="feature_reports_submitted", foreign_keys=[reported_by]
    )
    generated_feature: Mapped[Feature | None] = relationship(
        foreign_keys=[generated_feature_id],
    )


class FeatureQuery(Base):
    __tablename__ = "feature_queries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    feature_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("features.id", ondelete="CASCADE"),
        nullable=False,
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="borrador")
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    feature: Mapped[Feature] = relationship(back_populates="queries")
    creator: Mapped[User] = relationship(
        back_populates="feature_queries_created", foreign_keys=[created_by]
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    feature_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("features.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="backlog")
    asignado_a: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    feature: Mapped[Feature] = relationship(back_populates="tasks")
    project: Mapped[Project] = relationship(back_populates="tasks")
    assignee: Mapped[User | None] = relationship(
        back_populates="tasks_assigned", foreign_keys=[asignado_a]
    )
    creator: Mapped[User] = relationship(
        back_populates="tasks_created", foreign_keys=[created_by]
    )


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


class DocumentExposure(Base):
    __tablename__ = "document_exposures"
    __table_args__ = (
        CheckConstraint(
            "(document_id IS NOT NULL AND attachment_id IS NULL) "
            "OR (document_id IS NULL AND attachment_id IS NOT NULL)",
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
        ForeignKey("milestones.id", ondelete="CASCADE"),
        nullable=True,
    )
    feature_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("features.id", ondelete="CASCADE"),
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
    titulo_visible: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expuesto_por: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="document_exposures")
    milestone: Mapped[Milestone | None] = relationship()
    feature: Mapped[Feature | None] = relationship()
    document: Mapped[Document | None] = relationship(back_populates="exposures")
    attachment: Mapped[Attachment | None] = relationship(
        back_populates="exposures"
    )
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    user: Mapped[User] = relationship(back_populates="notifications")
    project: Mapped[Project] = relationship(back_populates="notifications")


class FeatureStateTransition(Base):
    __tablename__ = "feature_state_transitions"
    __table_args__ = (
        UniqueConstraint(
            "tipo_proyecto",
            "estado_desde",
            "estado_hasta",
            "rol_permitido",
            name="uq_feature_transition",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tipo_proyecto: Mapped[str] = mapped_column(String(20), nullable=False)
    estado_desde: Mapped[str] = mapped_column(String(40), nullable=False)
    estado_hasta: Mapped[str] = mapped_column(String(40), nullable=False)
    rol_permitido: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class TaskStateTransition(Base):
    __tablename__ = "task_state_transitions"
    __table_args__ = (
        UniqueConstraint(
            "estado_desde", "estado_hasta", "rol_permitido", name="uq_task_transition"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    estado_desde: Mapped[str] = mapped_column(String(20), nullable=False)
    estado_hasta: Mapped[str] = mapped_column(String(20), nullable=False)
    rol_permitido: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
