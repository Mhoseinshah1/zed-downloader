"""URL detection / platform resolution (app.providers.manager.manager)."""
import pytest

from app.models import Platform
from app.providers.manager import manager
from app.seed import PLATFORMS  # keep the fixtures in lockstep with the seed


async def _seed_platforms(session):
    for name, slug, url_regex, sort_order in PLATFORMS:
        session.add(Platform(name=name, slug=slug, url_regex=url_regex, sort_order=sort_order))
    await session.flush()


@pytest.mark.parametrize(
    "url,expected_slug",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
        ("https://www.instagram.com/p/Cabc123/", "instagram"),
        ("https://instagr.am/p/Cabc123/", "instagram"),
        ("https://www.tiktok.com/@user/video/123456", "tiktok"),
        ("https://vm.tiktok.com/ZMabc/", "tiktok"),
        ("https://twitter.com/user/status/1", "twitter"),
        ("https://x.com/user/status/1", "twitter"),
        # Any other http(s) URL falls through to the generic catch-all.
        ("https://example.com/media/clip", "generic"),
        ("http://some-random-site.org/video.mp4", "generic"),
    ],
)
async def test_resolve_platform_matches_expected(session, url, expected_slug):
    await _seed_platforms(session)
    platform = await manager.resolve_platform(session, url)
    assert platform is not None
    assert platform.slug == expected_slug


async def test_non_http_scheme_resolves_to_none(session):
    await _seed_platforms(session)
    assert await manager.resolve_platform(session, "ftp://x") is None


async def test_inactive_platform_is_skipped(session):
    # A deactivated platform must never match, even if its regex would.
    session.add(
        Platform(name="Off", slug="off", url_regex=r"^https?://", sort_order=1, is_active=False)
    )
    await _seed_platforms(session)
    platform = await manager.resolve_platform(session, "https://example.com/x")
    assert platform is not None
    assert platform.slug == "generic"


async def test_bad_regex_does_not_break_resolver(session):
    # A malformed regex configured from the panel must be skipped, not crash
    # the whole resolver (see ProviderManager.resolve_platform).
    session.add(Platform(name="Broken", slug="broken", url_regex=r"(unclosed", sort_order=5))
    await _seed_platforms(session)
    platform = await manager.resolve_platform(session, "https://example.com/x")
    assert platform is not None
    assert platform.slug == "generic"
