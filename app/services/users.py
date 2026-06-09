"""Gestión de usuarios (§4.1)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AuditLog,
    Comment,
    Notification,
    Project,
    ProjectMember,
    Task,
    TaskAssignee,
    User,
)
from app.schemas.users import UserUpdate
from app.security import hash_password


def update_user(db: Session, user: User, payload: UserUpdate) -> None:
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)

    changes = payload.model_dump(exclude_unset=True, exclude={"password"})
    if not changes and payload.password is None:
        return

    if "email" in changes:
        existing = db.scalar(
            select(User).where(User.email == changes["email"], User.id != user.id)
        )
        if existing:
            raise HTTPException(status_code=409, detail="El email ya está registrado")

    for field, nuevo in changes.items():
        setattr(user, field, nuevo)


def delete_user(db: Session, user: User) -> None:
    blockers: list[str] = []
    if db.scalar(select(exists().where(ProjectMember.user_id == user.id))):
        blockers.append("miembro de proyectos")
    if db.scalar(select(exists().where(Project.created_by == user.id))):
        blockers.append("creador de proyectos")
    if db.scalar(select(exists().where(TaskAssignee.user_id == user.id))):
        blockers.append("tareas asignadas")
    if db.scalar(select(exists().where(Task.created_by == user.id))):
        blockers.append("tareas creadas")
    if blockers:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede eliminar el usuario: {', '.join(blockers)}",
        )

    db.execute(delete(Notification).where(Notification.user_id == user.id))
    db.execute(delete(Comment).where(Comment.user_id == user.id))
    db.execute(delete(AuditLog).where(AuditLog.user_id == user.id))
    db.delete(user)
