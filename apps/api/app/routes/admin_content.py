"""Admin panel: ads, forced-join channels and editable bot texts."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Ad, BotText, ForcedJoinChannel
from app.routes.deps import require_role
from app.schemas.admin import (
    AdIn,
    AdOut,
    AdPatch,
    BotTextIn,
    BotTextOut,
    BotTextPatch,
    ForcedJoinIn,
    ForcedJoinOut,
    ForcedJoinPatch,
)

router = APIRouter(
    prefix="/api/admin",
    tags=["admin-content"],
    dependencies=[Depends(require_role("super_admin", "content_manager"))],
)


# --- Ads ----------------------------------------------------------------------

@router.get("/ads")
async def list_ads(db: AsyncSession = Depends(get_db)) -> dict:
    rows = await db.execute(select(Ad).order_by(Ad.id.desc()))
    return {"items": [AdOut.model_validate(a).model_dump(mode="json") for a in rows.scalars()]}


@router.post("/ads", response_model=AdOut, status_code=status.HTTP_201_CREATED)
async def create_ad(body: AdIn, db: AsyncSession = Depends(get_db)) -> Ad:
    ad = Ad(**body.model_dump())
    db.add(ad)
    await db.commit()
    return ad


@router.patch("/ads/{ad_id}", response_model=AdOut)
async def patch_ad(ad_id: int, body: AdPatch, db: AsyncSession = Depends(get_db)) -> Ad:
    ad = await db.get(Ad, ad_id)
    if ad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ad not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(ad, field, value)
    await db.commit()
    return ad


@router.delete("/ads/{ad_id}")
async def delete_ad(ad_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    ad = await db.get(Ad, ad_id)
    if ad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ad not found")
    await db.delete(ad)
    await db.commit()
    return {"ok": True}


# --- Forced-join channels ------------------------------------------------------

@router.get("/forced-join")
async def list_forced_join(db: AsyncSession = Depends(get_db)) -> dict:
    rows = await db.execute(
        select(ForcedJoinChannel).order_by(ForcedJoinChannel.sort_order.asc(), ForcedJoinChannel.id.asc())
    )
    return {"items": [ForcedJoinOut.model_validate(c).model_dump() for c in rows.scalars()]}


@router.post("/forced-join", response_model=ForcedJoinOut, status_code=status.HTTP_201_CREATED)
async def create_forced_join(body: ForcedJoinIn, db: AsyncSession = Depends(get_db)) -> ForcedJoinChannel:
    channel = ForcedJoinChannel(**body.model_dump())
    # Store usernames without a leading @ so get_chat_member lookups are uniform.
    channel.username = channel.username.lstrip("@")
    db.add(channel)
    await db.commit()
    return channel


@router.patch("/forced-join/{channel_id}", response_model=ForcedJoinOut)
async def patch_forced_join(channel_id: int, body: ForcedJoinPatch, db: AsyncSession = Depends(get_db)) -> ForcedJoinChannel:
    channel = await db.get(ForcedJoinChannel, channel_id)
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not found")
    data = body.model_dump(exclude_unset=True)
    if "username" in data and data["username"]:
        data["username"] = data["username"].lstrip("@")
    for field, value in data.items():
        setattr(channel, field, value)
    await db.commit()
    return channel


@router.delete("/forced-join/{channel_id}")
async def delete_forced_join(channel_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    channel = await db.get(ForcedJoinChannel, channel_id)
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not found")
    await db.delete(channel)
    await db.commit()
    return {"ok": True}


# --- Bot texts ----------------------------------------------------------------

@router.get("/bot-texts")
async def list_bot_texts(lang: str = "", db: AsyncSession = Depends(get_db)) -> dict:
    query = select(BotText).order_by(BotText.key.asc(), BotText.lang.asc())
    if lang:
        query = query.where(BotText.lang == lang)
    rows = await db.execute(query)
    return {"items": [BotTextOut.model_validate(t).model_dump() for t in rows.scalars()]}


@router.post("/bot-texts", response_model=BotTextOut, status_code=status.HTTP_201_CREATED)
async def create_bot_text(body: BotTextIn, db: AsyncSession = Depends(get_db)) -> BotText:
    text = BotText(**body.model_dump())
    db.add(text)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "a text with this key+lang already exists")
    return text


@router.patch("/bot-texts/{text_id}", response_model=BotTextOut)
async def patch_bot_text(text_id: int, body: BotTextPatch, db: AsyncSession = Depends(get_db)) -> BotText:
    text = await db.get(BotText, text_id)
    if text is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "text not found")
    text.value = body.value
    await db.commit()
    return text


@router.delete("/bot-texts/{text_id}")
async def delete_bot_text(text_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    text = await db.get(BotText, text_id)
    if text is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "text not found")
    await db.delete(text)
    await db.commit()
    return {"ok": True}
