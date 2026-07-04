"""Admin panel: download-request history (read-only)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import DownloadRequest
from app.routes.deps import require_role
from app.schemas.admin import DownloadOut

router = APIRouter(
    prefix="/api/admin",
    tags=["admin-downloads"],
    dependencies=[Depends(require_role("super_admin", "support"))],
)


@router.get("/downloads")
async def list_downloads(
    status_filter: str = Query(default="", alias="status"),
    user_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(DownloadRequest)
    if status_filter:
        query = query.where(DownloadRequest.status == status_filter)
    if user_id is not None:
        query = query.where(DownloadRequest.user_id == user_id)
    total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one())
    rows = await db.execute(
        query.order_by(DownloadRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = [DownloadOut.model_validate(d).model_dump(mode="json") for d in rows.scalars()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/downloads/{download_id}", response_model=DownloadOut)
async def get_download(download_id: int, db: AsyncSession = Depends(get_db)) -> DownloadRequest:
    row = await db.get(DownloadRequest, download_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "download not found")
    return row
