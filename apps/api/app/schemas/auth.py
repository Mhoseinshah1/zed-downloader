"""Auth request/response schemas."""
from pydantic import BaseModel, ConfigDict, EmailStr


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    # Optional: when provided, the refresh token is revoked too (not just the
    # access token from the Authorization header).
    refresh_token: str | None = None


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str | None = None
    role: str


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    admin: AdminOut | None = None
