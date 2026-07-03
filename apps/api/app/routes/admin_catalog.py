"""Admin panel: platforms + providers CRUD, provider test/balance."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Platform, Provider
from app.providers.manager import REGISTRY, build_provider
from app.routes.deps import require_role
from app.schemas.admin import (
    PlatformIn,
    PlatformOut,
    PlatformPatch,
    ProviderIn,
    ProviderOut,
    ProviderPatch,
)
from app.utils.security import encrypt_secret

router = APIRouter(
    prefix="/api/admin",
    tags=["admin-catalog"],
    dependencies=[Depends(require_role("super_admin", "content_manager"))],
)


# --- Platforms -----------------------------------------------------------------

@router.get("/platforms")
async def list_platforms(db: AsyncSession = Depends(get_db)) -> dict:
    rows = await db.execute(select(Platform).order_by(Platform.sort_order.asc(), Platform.id.asc()))
    return {"items": [PlatformOut.model_validate(p).model_dump() for p in rows.scalars()]}


@router.post("/platforms", response_model=PlatformOut, status_code=status.HTTP_201_CREATED)
async def create_platform(body: PlatformIn, db: AsyncSession = Depends(get_db)) -> Platform:
    platform = Platform(**body.model_dump())
    db.add(platform)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "slug already exists")
    return platform


@router.patch("/platforms/{platform_id}", response_model=PlatformOut)
async def patch_platform(platform_id: int, body: PlatformPatch, db: AsyncSession = Depends(get_db)) -> Platform:
    platform = await db.get(Platform, platform_id)
    if platform is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "platform not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(platform, field, value)
    await db.commit()
    return platform


@router.delete("/platforms/{platform_id}")
async def delete_platform(platform_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    platform = await db.get(Platform, platform_id)
    if platform is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "platform not found")
    await db.delete(platform)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "platform is referenced by providers/requests — deactivate it instead",
        )
    return {"ok": True}


# --- Providers -------------------------------------------------------------------

def _provider_out(row: Provider) -> ProviderOut:
    # The API key is write-only: the panel only ever learns whether one is set.
    return ProviderOut(
        id=row.id,
        name=row.name,
        slug=row.slug,
        platform_id=row.platform_id,
        provider_type=row.provider_type,
        has_api_key=bool(row.api_key_encrypted),
        base_url=row.base_url,
        priority=row.priority,
        timeout=row.timeout,
        settings=row.settings or {},
        is_active=row.is_active,
    )


def _encrypt_or_400(plaintext: str) -> str:
    try:
        return encrypt_secret(plaintext)
    except RuntimeError as exc:  # ENCRYPTION_KEY missing
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/providers")
async def list_providers(db: AsyncSession = Depends(get_db)) -> dict:
    rows = await db.execute(select(Provider).order_by(Provider.priority.asc(), Provider.id.asc()))
    return {"items": [_provider_out(p).model_dump() for p in rows.scalars()]}


@router.post("/providers", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(body: ProviderIn, db: AsyncSession = Depends(get_db)) -> ProviderOut:
    if body.provider_type not in REGISTRY:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"unknown provider_type '{body.provider_type}' — registered: {sorted(REGISTRY)}",
        )
    if await db.get(Platform, body.platform_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "platform not found")
    provider = Provider(
        name=body.name,
        slug=body.slug,
        platform_id=body.platform_id,
        provider_type=body.provider_type,
        api_key_encrypted=_encrypt_or_400(body.api_key) if body.api_key else None,
        base_url=body.base_url,
        priority=body.priority,
        timeout=body.timeout,
        settings=body.settings,
        is_active=body.is_active,
    )
    db.add(provider)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "slug already exists")
    return _provider_out(provider)


@router.patch("/providers/{provider_id}", response_model=ProviderOut)
async def patch_provider(provider_id: int, body: ProviderPatch, db: AsyncSession = Depends(get_db)) -> ProviderOut:
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider not found")
    data = body.model_dump(exclude_unset=True)
    if "provider_type" in data and data["provider_type"] not in REGISTRY:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown provider_type")
    if "platform_id" in data and await db.get(Platform, data["platform_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "platform not found")
    if "api_key" in data:
        raw = data.pop("api_key")
        # "" clears the stored key, anything else replaces it.
        provider.api_key_encrypted = _encrypt_or_400(raw) if raw else None
    for field, value in data.items():
        setattr(provider, field, value)
    await db.commit()
    return _provider_out(provider)


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider not found")
    await db.delete(provider)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "provider is referenced by download history — deactivate it instead",
        )
    return {"ok": True}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(Provider, provider_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider not found")
    try:
        provider = build_provider(row)
        ok = await provider.health_check()
        return {"ok": bool(ok)}
    except Exception as exc:  # never 500 the panel over a broken provider
        return {"ok": False, "error": str(exc)[:300]}


@router.get("/providers/{provider_id}/balance")
async def provider_balance(provider_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(Provider, provider_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider not found")
    try:
        provider = build_provider(row)
        return await provider.get_balance()
    except Exception as exc:
        return {"supported": True, "ok": False, "error": str(exc)[:300]}
