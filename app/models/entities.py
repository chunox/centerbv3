"""
ORM models â€” Center MVP1
20 tablas. Fuente de verdad del schema junto con Alembic.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# ID de 36 chars (UUID string). Compatible SQLite y PostgreSQL.
ID = String(36)

from app.database import Base


# â”€â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def gen_uuid() -> str:
    return str(uuid.uuid4())


# â”€â”€â”€ Usuarios y autenticaciÃ³n â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relations
    org_memberships: Mapped[list["OrganizationMember"]] = relationship(back_populates="user")
    project_memberships: Mapped[list["ProjectMember"]] = relationship(back_populates="user")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# â”€â”€â”€ Organizaciones â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="activa")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relations
    members: Mapped[list["OrganizationMember"]] = relationship(back_populates="organization")
    invites: Mapped[list["OrganizationInvite"]] = relationship(back_populates="organization")
    projects: Mapped[list["Project"]] = relationship(back_populates="organization")


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(ID, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rol: Mapped[str] = mapped_column(String(20), nullable=False, default="member")  # owner | admin | member
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relations
    organization: Mapped["Organization"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="org_memberships")


class OrganizationInvite(Base):
    __tablename__ = "organization_invites"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(ID, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    rol: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    invited_by: Mapped[str] = mapped_column(ID, ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relations
    organization: Mapped["Organization"] = relationship(back_populates="invites")


# â”€â”€â”€ Proyectos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(ID, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    pack_slug: Mapped[str] = mapped_column(String(40), nullable=False)        # software-waterfall | software-scrum
    template_slug: Mapped[str] = mapped_column(String(40), nullable=False)    # t3_interno_clasico | t6_scrum_interno
    delivery_mode: Mapped[str] = mapped_column(String(20), nullable=False)    # waterfall | scrum
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="activo")
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    # settings: { effort_unit, hours_per_story_point, feature_workflow, ... }
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(ID, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relations
    organization: Mapped["Organization"] = relationship(back_populates="projects")
    roles: Mapped[list["ProjectRole"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    members: Mapped[list["ProjectMember"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    records: Mapped[list["ProjectRecord"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectRole(Base):
    __tablename__ = "project_roles"
    __table_args__ = (UniqueConstraint("project_id", "slug"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(40), nullable=False)   # pm | tech_lead | dev | qa
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(40), nullable=False, default="#6366f1")

    # Relations
    project: Mapped["Project"] = relationship(back_populates="roles")
    members: Mapped[list["ProjectMember"]] = relationship(back_populates="role")


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", "role_id"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(ID, ForeignKey("project_roles.id", ondelete="CASCADE"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relations
    project: Mapped["Project"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="project_memberships")
    role: Mapped["ProjectRole"] = relationship(back_populates="members")


# â”€â”€â”€ Records (modelo genÃ©rico) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ProjectRecord(Base):
    __tablename__ = "project_records"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    # record_type: milestone | feature | task | sprint | product_backlog
    record_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(ID, ForeignKey("project_records.id", ondelete="SET NULL"), index=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    # estimacion: siempre en horas (unidad canÃ³nica). ConversiÃ³n a SP en display.
    estimacion: Mapped[float | None] = mapped_column(Numeric(10, 2))
    # extra: scrum_role (epic|story|dev|subtask), otros campos pack-especÃ­ficos
    extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(ID, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relations
    project: Mapped["Project"] = relationship(back_populates="records")
    parent: Mapped["ProjectRecord | None"] = relationship(remote_side="ProjectRecord.id", foreign_keys=[parent_id], overlaps="children")
    children: Mapped[list["ProjectRecord"]] = relationship(foreign_keys=[parent_id], overlaps="parent")
    assignees: Mapped[list["ProjectRecordAssignee"]] = relationship(back_populates="record", cascade="all, delete-orphan")
    active_blockers: Mapped[list["ProjectRecordBlocker"]] = relationship(
        back_populates="record",
        primaryjoin="and_(ProjectRecordBlocker.record_id == ProjectRecord.id, ProjectRecordBlocker.resolved_at == None)",
        viewonly=True,
    )
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="record",
        primaryjoin="and_(Comment.entity_type == 'record', Comment.entity_id == foreign(ProjectRecord.id))",
        foreign_keys="[Comment.entity_id]",
        viewonly=True,
    )


class ProjectRecordAssignee(Base):
    __tablename__ = "project_record_assignees"
    __table_args__ = (UniqueConstraint("record_id", "user_id"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    record_id: Mapped[str] = mapped_column(ID, ForeignKey("project_records.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relations
    record: Mapped["ProjectRecord"] = relationship(back_populates="assignees")
    user: Mapped["User"] = relationship()


class ProjectRecordBlocker(Base):
    __tablename__ = "project_record_blockers"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    record_id: Mapped[str] = mapped_column(ID, ForeignKey("project_records.id", ondelete="CASCADE"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(ID, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    resolved_by: Mapped[str | None] = mapped_column(ID, ForeignKey("users.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)

    # Relations
    record: Mapped["ProjectRecord"] = relationship(back_populates="active_blockers", foreign_keys=[record_id])


class ProjectRecordDependency(Base):
    """predecessor debe estar completado antes de que successor pueda avanzar."""
    __tablename__ = "project_record_dependencies"
    __table_args__ = (UniqueConstraint("predecessor_id", "successor_id"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    predecessor_id: Mapped[str] = mapped_column(ID, ForeignKey("project_records.id", ondelete="CASCADE"), nullable=False, index=True)
    successor_id: Mapped[str] = mapped_column(ID, ForeignKey("project_records.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(ID, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# â”€â”€â”€ Scrum â€” ceremonias â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ScrumCeremonySession(Base):
    __tablename__ = "scrum_ceremony_sessions"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    # sprint_id: referencia al ProjectRecord de tipo sprint
    sprint_id: Mapped[str | None] = mapped_column(ID, ForeignKey("project_records.id", ondelete="SET NULL"), index=True)
    session_type: Mapped[str] = mapped_column(String(20), nullable=False)  # planning | daily | retro | review
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")  # pendiente | activa | cerrada
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[str] = mapped_column(ID, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relations
    entries: Mapped[list["ScrumCeremonyEntry"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class ScrumCeremonyEntry(Base):
    __tablename__ = "scrum_ceremony_entries"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    session_id: Mapped[str] = mapped_column(ID, ForeignKey("scrum_ceremony_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(ID, ForeignKey("users.id"), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # payload: contenido libre segÃºn entry_type (standup, vote, retro_item, etc.)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relations
    session: Mapped["ScrumCeremonySession"] = relationship(back_populates="entries")


# â”€â”€â”€ Hub â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class HubEntry(Base):
    __tablename__ = "hub_entries"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(ID, ForeignKey("users.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)  # nota | decision | riesgo | documento
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    contenido: Mapped[str | None] = mapped_column(Text)  # Markdown
    # record_id: si la entrada estÃ¡ vinculada a un record especÃ­fico
    record_id: Mapped[str | None] = mapped_column(ID, ForeignKey("project_records.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# â”€â”€â”€ Adjuntos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(ID, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by: Mapped[str] = mapped_column(ID, ForeignKey("users.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relations
    relations: Mapped[list["AttachmentRelation"]] = relationship(back_populates="attachment", cascade="all, delete-orphan")


class AttachmentRelation(Base):
    """PolimÃ³rfico: adjunta un archivo a cualquier entidad (record, hub_entry, comment)."""
    __tablename__ = "attachment_relations"
    __table_args__ = (UniqueConstraint("attachment_id", "entity_type", "entity_id"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    attachment_id: Mapped[str] = mapped_column(ID, ForeignKey("attachments.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)   # record | hub_entry
    entity_id: Mapped[str] = mapped_column(ID, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relations
    attachment: Mapped["Attachment"] = relationship(back_populates="relations")


# â”€â”€â”€ Comentarios â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class Comment(Base):
    """PolimÃ³rfico: comentarios en records o hub_entries."""
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(ID, ForeignKey("users.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)   # record | hub_entry
    entity_id: Mapped[str] = mapped_column(ID, nullable=False, index=True)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relations (viewonly â€” join polimÃ³rfico)
    record: Mapped["ProjectRecord | None"] = relationship(
        back_populates="comments",
        primaryjoin="and_(Comment.entity_type == 'record', Comment.entity_id == foreign(ProjectRecord.id))",
        foreign_keys="[Comment.entity_id]",
        viewonly=True,
    )


# â”€â”€â”€ Audit logs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(ID, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ID, ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    actor_id: Mapped[str] = mapped_column(ID, ForeignKey("users.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(ID, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False)   # created | updated | deleted | transitioned
    # changes: { field: [old, new] } para updates; { to_status } para transiciones
    changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


# â”€â”€â”€ Preferencias de vista â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ProjectViewPreference(Base):
    """Preferencias por usuario Ã— vista Ã— proyecto (filtros, columnas visibles, agrupaciÃ³n)."""
    __tablename__ = "project_view_preferences"
    __table_args__ = (UniqueConstraint("project_id", "user_id", "view_key"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    view_key: Mapped[str] = mapped_column(String(80), nullable=False)
    # preferences: { filters, visible_columns, grouping, sort, ... }
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

