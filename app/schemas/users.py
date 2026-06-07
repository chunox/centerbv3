from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """Lo que envía el cliente al crear un usuario (sin password_hash)."""

    nombre: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    avatar_url: str | None = Field(default=None, max_length=500)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserRead(BaseModel):
    """Lo que devuelve la API — nunca incluye password_hash."""

    id: UUID
    nombre: str
    email: str
    avatar_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
