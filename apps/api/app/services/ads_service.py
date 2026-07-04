"""Ad selection: pick a random active ad, weighted by `weight`."""
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ad


async def get_random_ad(session: AsyncSession) -> Ad | None:
    """Return one active ad chosen with probability proportional to its
    weight, or None when there are no active ads."""
    ads = (await session.execute(select(Ad).where(Ad.is_active.is_(True)))).scalars().all()
    if not ads:
        return None
    weights = [max(1, ad.weight) for ad in ads]
    return random.choices(ads, weights=weights, k=1)[0]
