"""Provider fallback orchestration (ProviderManager.download).

Fallback policy under test:
- RECOVERABLE errors (provider_down / rate_limited / unknown_error) -> try
  the next provider by priority.
- Content-fatal errors (private_content / file_too_large / duration_too_long)
  -> raise immediately, never touch a later provider.
"""
import pytest

from app.models import Platform, Provider
from app.providers.base import (
    BaseProvider,
    DownloadError,
    DownloadResult,
    ProviderException,
)
from app.providers.manager import REGISTRY, manager


class RecordingProvider(BaseProvider):
    """Fake provider whose behaviour is driven by its DB row `settings`:

    settings = {"tag": <label>, "code": <DownloadError value or None>}
    A None code means "succeed"; anything else is raised as a
    ProviderException. Every invocation records its tag so a test can prove
    which providers were (and were not) tried.
    """

    provider_type = "fake"
    calls: list[str] = []

    def validate_url(self, url: str) -> bool:
        return True

    async def get_metadata(self, url: str):  # pragma: no cover - unused
        raise NotImplementedError

    async def get_formats(self, url: str):  # pragma: no cover - unused
        return []

    async def download(self, url: str, dest_dir: str) -> DownloadResult:
        tag = self.settings.get("tag")
        RecordingProvider.calls.append(tag)
        code = self.settings.get("code")
        if code:
            raise ProviderException(DownloadError(code), f"{tag} raised {code}")
        return DownloadResult(
            file_path=f"{dest_dir}/{tag}.mp4",
            file_name=f"{tag}.mp4",
            file_size=123,
            file_type="video",
        )


@pytest.fixture
def fake_provider():
    RecordingProvider.calls = []
    REGISTRY["fake"] = RecordingProvider
    try:
        yield RecordingProvider
    finally:
        REGISTRY.pop("fake", None)
        RecordingProvider.calls = []


async def _make_platform_with_providers(session, behaviors):
    """behaviors: list of (tag, code) in ascending priority order."""
    platform = Platform(name="Fake", slug="fake", url_regex=r"fake")
    session.add(platform)
    await session.flush()
    rows = []
    for i, (tag, code) in enumerate(behaviors):
        row = Provider(
            name=tag,
            slug=tag,
            platform_id=platform.id,
            provider_type="fake",
            priority=(i + 1) * 10,  # ascending -> tried in this order
            settings={"tag": tag, "code": code},
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return platform, rows


@pytest.mark.parametrize("recoverable", ["provider_down", "rate_limited", "unknown_error"])
async def test_falls_back_on_recoverable_error(session, fake_provider, recoverable):
    platform, rows = await _make_platform_with_providers(
        session, [("p1", recoverable), ("p2", None)]
    )
    used_row, result = await manager.download(session, "fake://x", platform.id, "/tmp")

    # First provider failed recoverably, second one served the download.
    assert used_row.slug == "p2"
    assert result.file_name == "p2.mp4"
    assert fake_provider.calls == ["p1", "p2"]


async def test_falls_back_across_multiple_recoverable_providers(session, fake_provider):
    platform, rows = await _make_platform_with_providers(
        session, [("p1", "provider_down"), ("p2", "rate_limited"), ("p3", None)]
    )
    used_row, result = await manager.download(session, "fake://x", platform.id, "/tmp")
    assert used_row.slug == "p3"
    assert fake_provider.calls == ["p1", "p2", "p3"]


async def test_all_recoverable_failures_raise_last_error(session, fake_provider):
    platform, rows = await _make_platform_with_providers(
        session, [("p1", "provider_down"), ("p2", "rate_limited")]
    )
    with pytest.raises(ProviderException) as exc:
        await manager.download(session, "fake://x", platform.id, "/tmp")
    # Last error encountered is surfaced; every provider was attempted.
    assert exc.value.code == DownloadError.RATE_LIMITED
    assert fake_provider.calls == ["p1", "p2"]


@pytest.mark.parametrize(
    "fatal", ["private_content", "file_too_large", "duration_too_long"]
)
async def test_fatal_error_raises_immediately_without_fallback(session, fake_provider, fatal):
    platform, rows = await _make_platform_with_providers(
        session, [("p1", fatal), ("p2", None)]
    )
    with pytest.raises(ProviderException) as exc:
        await manager.download(session, "fake://x", platform.id, "/tmp")

    assert exc.value.code == DownloadError(fatal)
    # Crucially: the second (working) provider was never tried.
    assert fake_provider.calls == ["p1"]


async def test_no_active_provider_raises_provider_down(session, fake_provider):
    platform = Platform(name="Empty", slug="empty", url_regex=r"empty")
    session.add(platform)
    await session.flush()
    with pytest.raises(ProviderException) as exc:
        await manager.download(session, "empty://x", platform.id, "/tmp")
    assert exc.value.code == DownloadError.PROVIDER_DOWN
