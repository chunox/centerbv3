from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

OrgEstado = Literal["activa", "suspendida"]
OrgMemberRol = Literal["owner", "admin", "member"]
OrgInviteRol = Literal["admin", "member"]


class OrganizationCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    slug: str | None = Field(default=None, min_length=1, max_length=80)


class OrganizationUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    slug: str | None = Field(default=None, min_length=1, max_length=80)


class OrganizationRead(BaseModel):
    id: UUID
    nombre: str
    slug: str
    estado: OrgEstado
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrganizationMemberRead(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: UUID
    rol: OrgMemberRol
    joined_at: datetime

    model_config = {"from_attributes": True}


class OrganizationMemberCreate(BaseModel):
    user_id: UUID
    rol: OrgMemberRol = "member"


class OrganizationInviteCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    rol: OrgInviteRol = "member"


class OrganizationInviteRead(BaseModel):
    id: UUID
    organization_id: UUID
    email: str
    rol: OrgInviteRol
    token: str
    expires_at: datetime
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class OrganizationJoin(BaseModel):
    token: str = Field(min_length=8, max_length=64)
