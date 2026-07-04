"""Admin token revocation (logout blacklist).

A decoded JWT payload carries a `jti` (unique id) and `exp` (expiry). To log
a token out we store its jti in `revoked_tokens` until its natural expiry;
every authenticated request and every refresh checks the blacklist. Expired
rows are purged by worker housekeeping.
"""
import datetime as dt

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import utcnow
from app.models import RevokedToken


def _exp_datetime(payload: dict) -> dt.datetime:
    exp = payload.get("exp")
    if exp is None:
        # No expiry claim: keep the blacklist row a conservative 30 days.
        return utcnow() + dt.timedelta(days=30)
    return dt.datetime.fromtimestamp(int(exp), tz=dt.timezone.utc)


async def revoke_token(session: AsyncSession, payload: dict) -> None:
    """Blacklist a decoded token by its jti (idempotent)."""
    jti = payload.get("jti")
    if not jti:
        # Legacy token minted before jti existed — nothing to blacklist by id.
        return
    exists = await session.execute(select(RevokedToken.id).where(RevokedToken.jti == jti))
    if exists.scalar_one_or_none() is not None:
        return
    try:
        # SAVEPOINT: a concurrent duplicate-jti insert must roll back ONLY this
        # insert, never earlier work in the same request transaction. (logout
        # revokes two tokens on one session; a plain session.rollback() here
        # would also discard the first, already-flushed revocation.) The add
        # is inside the nested block so the savepoint rollback fully discards it.
        async with session.begin_nested():
            session.add(
                RevokedToken(
                    jti=jti,
                    admin_id=int(payload["sub"]) if payload.get("sub") else None,
                    token_type=payload.get("type", "access"),
                    expires_at=_exp_datetime(payload),
                )
            )
    except IntegrityError:
        # Concurrent revoke of the same jti — already blacklisted, fine.
        pass


async def is_token_revoked(session: AsyncSession, payload: dict) -> bool:
    jti = payload.get("jti")
    if not jti:
        return False
    result = await session.execute(select(RevokedToken.id).where(RevokedToken.jti == jti))
    return result.scalar_one_or_none() is not None


async def purge_expired(session: AsyncSession) -> int:
    """Delete blacklist rows whose token has expired anyway. Returns count."""
    result = await session.execute(
        delete(RevokedToken).where(RevokedToken.expires_at < utcnow())
    )
    return result.rowcount or 0
