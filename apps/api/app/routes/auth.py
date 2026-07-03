"""Admin-panel authentication: login / refresh / logout / me."""
import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, utcnow
from app.models import Admin
from app.routes.deps import get_current_admin
from app.schemas.auth import AdminOut, LoginIn, RefreshIn, TokenPairOut
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)

router = APIRouter(prefix="/api/admin", tags=["auth"])


@router.post("/auth/login", response_model=TokenPairOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)) -> TokenPairOut:
    result = await db.execute(select(Admin).where(Admin.email == body.email.lower()))
    admin = result.scalar_one_or_none()
    # Single generic error for bad email OR bad password — no user enumeration.
    if admin is None or not admin.is_active or not verify_password(body.password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    admin.last_login_at = utcnow()
    await db.commit()
    return TokenPairOut(
        access_token=create_access_token(admin.id, admin.role),
        refresh_token=create_refresh_token(admin.id),
        admin=AdminOut.model_validate(admin),
    )


@router.post("/auth/refresh", response_model=TokenPairOut)
async def refresh(body: RefreshIn, db: AsyncSession = Depends(get_db)) -> TokenPairOut:
    try:
        payload = decode_token(body.refresh_token)
    except pyjwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh token required")
    admin = await db.get(Admin, int(payload.get("sub", 0)))
    if admin is None or not admin.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "admin not found or disabled")
    return TokenPairOut(
        access_token=create_access_token(admin.id, admin.role),
        refresh_token=create_refresh_token(admin.id),
        admin=AdminOut.model_validate(admin),
    )


@router.post("/auth/logout")
async def logout(admin: Admin = Depends(get_current_admin)) -> dict:
    # Stateless JWTs: the client discards its tokens. NOTE: a server-side
    # refresh-token blacklist is a v2 hardening item.
    return {"ok": True}


@router.get("/me", response_model=AdminOut)
async def me(admin: Admin = Depends(get_current_admin)) -> Admin:
    return admin
