"""Shared route dependencies: admin JWT auth, role gate, internal secret."""
import hmac

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Admin
from app.services.auth_service import is_token_revoked
from app.utils.security import decode_token

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


async def get_current_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Admin:
    if creds is None:
        raise _unauthorized("missing bearer token")
    try:
        payload = decode_token(creds.credentials)
    except pyjwt.PyJWTError:
        raise _unauthorized("invalid or expired token")
    if payload.get("type") != "access":
        raise _unauthorized("access token required")
    if await is_token_revoked(db, payload):
        raise _unauthorized("token has been revoked")
    admin = await db.get(Admin, int(payload.get("sub", 0)))
    if admin is None or not admin.is_active:
        raise _unauthorized("admin not found or disabled")
    return admin


def require_role(*roles: str):
    """Dependency factory: allow listed roles (owner always passes)."""

    async def dependency(admin: Admin = Depends(get_current_admin)) -> Admin:
        if admin.role == "owner" or admin.role in roles:
            return admin
        raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role for this action")

    return dependency


async def require_internal_secret(x_internal_secret: str = Header(default="")) -> None:
    """Guard for /api/internal/*: shared secret between bot and api."""
    expected = get_settings().TELEGRAM_WEBHOOK_SECRET
    if not expected or not hmac.compare_digest(x_internal_secret, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad internal secret")
