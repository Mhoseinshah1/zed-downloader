"""Admin panel: user + group management."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Group, User
from app.routes.deps import require_role
from app.schemas.admin import GroupOut, GroupPatch, UserOut, UserPatch

router = APIRouter(
    prefix="/api/admin",
    tags=["admin-users"],
    dependencies=[Depends(require_role("super_admin", "support"))],
)


@router.get("/users")
async def list_users(
    search: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(User)
    if search:
        like = f"%{search}%"
        clauses = [
            User.username.ilike(like),
            User.first_name.ilike(like),
            User.last_name.ilike(like),
        ]
        try:
            numeric = int(search)
        except ValueError:
            numeric = None
        # Only bind values that fit the BIGINT column — an out-of-range
        # literal would make the whole query error out.
        if numeric is not None and -(2**63) <= numeric < 2**63:
            clauses.append(User.telegram_id == numeric)
        query = query.where(or_(*clauses))

    total = int(
        (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    )
    rows = await db.execute(
        query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = [UserOut.model_validate(u).model_dump(mode="json") for u in rows.scalars()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def _get_user_or_404(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return user


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)) -> User:
    return await _get_user_or_404(db, user_id)


@router.patch("/users/{user_id}", response_model=UserOut)
async def patch_user(user_id: int, body: UserPatch, db: AsyncSession = Depends(get_db)) -> User:
    user = await _get_user_or_404(db, user_id)
    if body.language is not None:
        user.language = body.language
    if body.is_blocked is not None:
        user.is_blocked = body.is_blocked
    await db.commit()
    return user


@router.post("/users/{user_id}/block", response_model=UserOut)
async def block_user(user_id: int, db: AsyncSession = Depends(get_db)) -> User:
    user = await _get_user_or_404(db, user_id)
    user.is_blocked = True
    await db.commit()
    return user


@router.post("/users/{user_id}/unblock", response_model=UserOut)
async def unblock_user(user_id: int, db: AsyncSession = Depends(get_db)) -> User:
    user = await _get_user_or_404(db, user_id)
    user.is_blocked = False
    await db.commit()
    return user


@router.get("/groups")
async def list_groups(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    total = int((await db.execute(select(func.count(Group.id)))).scalar_one())
    rows = await db.execute(
        select(Group).order_by(Group.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = [GroupOut.model_validate(g).model_dump(mode="json") for g in rows.scalars()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.patch("/groups/{group_id}", response_model=GroupOut)
async def patch_group(group_id: int, body: GroupPatch, db: AsyncSession = Depends(get_db)) -> Group:
    group = await db.get(Group, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "group not found")
    if body.title is not None:
        group.title = body.title
    if body.is_enabled is not None:
        group.is_enabled = body.is_enabled
    if body.daily_limit is not None:
        # NOTE: send -1 from the panel to clear the limit (None = unlimited).
        group.daily_limit = None if body.daily_limit < 0 else body.daily_limit
    await db.commit()
    return group
