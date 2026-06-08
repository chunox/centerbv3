from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.organizations import OrganizationRead
from app.schemas.users import UserRead


class AuthRegister(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class AuthLogin(BaseModel):
    email: str
    password: str


class AuthSwitchOrganization(BaseModel):
    organization_id: UUID


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
    organization_id: UUID | None = None
    organizations: list[OrganizationRead] = []


class AuthForgotPassword(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class AuthResetPassword(BaseModel):
    token: str = Field(min_length=16, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class AuthMessageResponse(BaseModel):
    message: str
