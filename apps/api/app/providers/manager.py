"""Provider registry + platform resolution + fallback orchestration.

To add a provider:
1. Write a BaseProvider subclass in app/providers/your_provider.py.
2. Add one line to REGISTRY below.
3. Create a provider row from the admin panel (or seed) with
   provider_type = the registry key.
"""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Platform, Provider
from app.providers.apify_instagram_provider import ApifyInstagramProvider
from app.providers.base import (
    BaseProvider,
    DownloadError,
    DownloadResult,
    ProviderException,
    RECOVERABLE_ERRORS,
)
from app.providers.ytdlp_provider import YtDlpProvider
from app.utils.security import decrypt_secret

REGISTRY: dict[str, type[BaseProvider]] = {
    "ytdlp": YtDlpProvider,
    "apify": ApifyInstagramProvider,
}


def build_provider(row: Provider) -> BaseProvider:
    """Instantiate the implementation class for a provider DB row,
    decrypting its API key on the way."""
    cls = REGISTRY.get(row.provider_type)
    if cls is None:
        raise ProviderException(
            DownloadError.UNKNOWN_ERROR, f"unknown provider_type: {row.provider_type}"
        )
    api_key = decrypt_secret(row.api_key_encrypted) if row.api_key_encrypted else None
    return cls(
        api_key=api_key,
        base_url=row.base_url,
        timeout=row.timeout or 300,
        settings=row.settings or {},
    )


async def providers_for_platform(session: AsyncSession, platform_id: int) -> list[Provider]:
    """Active providers for a platform, lowest priority number first."""
    result = await session.execute(
        select(Provider)
        .where(Provider.platform_id == platform_id, Provider.is_active.is_(True))
        .order_by(Provider.priority.asc(), Provider.id.asc())
    )
    return list(result.scalars())


class ProviderManager:
    async def resolve_platform(self, session: AsyncSession, url: str) -> Platform | None:
        """First active platform whose url_regex matches the URL."""
        result = await session.execute(
            select(Platform)
            .where(Platform.is_active.is_(True))
            .order_by(Platform.sort_order.asc(), Platform.id.asc())
        )
        for platform in result.scalars():
            try:
                if re.search(platform.url_regex, url, re.IGNORECASE):
                    return platform
            except re.error:
                # NOTE: a bad regex configured from the panel must not take
                # the whole resolver down — skip it.
                continue
        return None

    async def download(
        self, session: AsyncSession, url: str, platform_id: int, dest_dir: str
    ) -> tuple[Provider, DownloadResult]:
        """Try each active provider in priority order.

        Fallback policy: continue to the next provider only on RECOVERABLE
        errors (provider_down / rate_limited / unknown_error). Content-fatal
        errors — private_content, file_too_large, duration_too_long, and also
        not_found / unsupported_url — raise immediately: no provider can fix
        those.
        """
        rows = await providers_for_platform(session, platform_id)
        if not rows:
            raise ProviderException(DownloadError.PROVIDER_DOWN, "no active provider for platform")

        last_exc: ProviderException | None = None
        for row in rows:
            provider = build_provider(row)
            try:
                result = await provider.download(url, dest_dir)
                return row, result
            except ProviderException as exc:
                if exc.code in RECOVERABLE_ERRORS:
                    last_exc = exc
                    continue
                raise
            except Exception as exc:  # defensive: a provider bug is recoverable
                last_exc = ProviderException(DownloadError.UNKNOWN_ERROR, str(exc)[:500])
                continue

        assert last_exc is not None
        raise last_exc


manager = ProviderManager()
