"""Admin panel: key/value settings management."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Setting
from app.routes.deps import require_role
from app.schemas.admin import SettingIn, SettingOut

router = APIRouter(
    prefix="/api/admin",
    tags=["admin-settings"],
    dependencies=[Depends(require_role("super_admin"))],
)


@router.get("/settings")
async def list_settings(db: AsyncSession = Depends(get_db)) -> dict:
    rows = await db.execute(select(Setting).order_by(Setting.key.asc()))
    return {"items": [SettingOut.model_validate(s).model_dump() for s in rows.scalars()]}


@router.put("/settings/{key}", response_model=SettingOut)
async def upsert_setting(key: str, body: SettingIn, db: AsyncSession = Depends(get_db)) -> Setting:
    row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    if row is None:
        # NOTE: creating unknown keys is allowed so operators can pre-stage
        # settings the code reads with a default; existing keys keep their
        # description.
        row = Setting(key=key, value=body.value)
        db.add(row)
    else:
        row.value = body.value
    await db.commit()
    return row


@router.get("/settings/{key}", response_model=SettingOut)
async def get_setting(key: str, db: AsyncSession = Depends(get_db)) -> Setting:
    row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "setting not found")
    return row
