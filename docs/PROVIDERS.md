# Download Providers

A **provider** is a strategy for downloading media from a platform (yt-dlp, a third-party API, ...). Platforms (Instagram, YouTube, ...) and their providers are configured in the database and managed from the admin panel; the code only ships provider *implementations* in a registry.

> **Legal scope — read first.** Providers handle **public, permitted content only**. Anything that would require authentication — private posts, subscriber-only or age-gated media — must raise `ProviderException(DownloadError.PRIVATE_CONTENT)`. **Never add cookie files, logins, session tokens, or any other bypass option to a provider.** Pull requests that do will not be accepted.

## Architecture

```
URL ──▶ ProviderManager.resolve_platform()      first active Platform whose
                                                url_regex matches the URL
      ▶ providers_for_platform()                active providers for that
                                                platform, priority ASC
      ▶ for each provider row:
          build_provider(row)                   registry lookup by provider_type,
                                                Fernet-decrypt the API key
          provider.download(url, dest_dir)      success → deliver file
                                                recoverable error → try next
                                                content-fatal error → raise now
```

Key files (all under `apps/api/app/providers/`):

| File | Contents |
|---|---|
| `base.py` | `BaseProvider` ABC, `DownloadError` codes, `ProviderException`, result dataclasses |
| `manager.py` | `REGISTRY`, `build_provider()`, `ProviderManager` (platform resolution + fallback) |
| `ytdlp_provider.py` | Built-in yt-dlp based provider (registry key `ytdlp`) |
| `apify_instagram_provider.py` | Built-in Apify Instagram provider (registry key `apify`) |

### `BaseProvider` interface

| Method | Purpose |
|---|---|
| `validate_url(url) -> bool` | Cheap syntactic check: could this provider handle the URL at all? |
| `get_metadata(url) -> MediaMetadata` | Title, duration, uploader, thumbnail, formats (async) |
| `get_formats(url) -> list[MediaFormat]` | Available formats/qualities (async) |
| `download(url, dest_dir) -> DownloadResult` | Do the download; must enforce size/duration guards and raise `PRIVATE_CONTENT` for private media (async) |
| `get_balance() -> dict` | Remaining upstream API credit; default `{"supported": False}` (async) |
| `health_check() -> bool` | Is the provider usable right now; default `True` (async) |

Constructor keyword args (populated from the provider's DB row): `api_key`, `base_url`, `timeout`, `settings` (free-form dict for per-provider options).

### `DownloadError` codes

| Code | Meaning | Fallback? |
|---|---|---|
| `unsupported_url` | Provider/platform cannot handle this URL | No — raise immediately |
| `private_content` | Content requires login / is not public | No — raise immediately (legal refusal path) |
| `not_found` | Content deleted or never existed | No — raise immediately |
| `provider_down` | Upstream service unreachable / erroring | **Yes** — try next provider |
| `rate_limited` | Upstream throttled us | **Yes** — try next provider |
| `file_too_large` | Exceeds `MAX_FILE_SIZE_MB` | No — raise immediately |
| `duration_too_long` | Exceeds `MAX_DURATION_SECONDS` | No — raise immediately |
| `unknown_error` | Anything unexpected (also raised for provider bugs) | **Yes** — try next provider |

The worker maps the final error code to a localized (fa/en) message and sends it to the user's chat.

### Fallback policy (`ProviderManager.download`)

Providers for the matched platform are tried in **priority order** (lowest number first). The manager moves on to the next provider only for the *recoverable* codes — `provider_down`, `rate_limited`, `unknown_error` — because a different provider might still succeed. Codes that describe the **content itself** (`private_content`, `file_too_large`, `duration_too_long`, plus `not_found` / `unsupported_url`) raise immediately: no provider can fix those, so the manager fails fast instead of hammering every upstream. If every provider fails recoverably, the last error is raised.

### API keys are encrypted at rest

Provider API keys are stored in the `providers` table **Fernet-encrypted** with the root `ENCRYPTION_KEY` env var and decrypted only inside `build_provider()` at call time. Keys are entered via the admin panel and never returned in plaintext by the API.

## Adding a provider — exact steps

**1.** Write the class in `apps/api/app/providers/your_provider.py` implementing `BaseProvider`:

```python
"""Example provider skeleton — public content only."""
from app.providers.base import (
    BaseProvider,
    DownloadError,
    DownloadResult,
    MediaFormat,
    MediaMetadata,
    ProviderException,
)


class YourProvider(BaseProvider):
    provider_type = "your_provider"  # must equal the REGISTRY key

    def validate_url(self, url: str) -> bool:
        return "example-platform.com/" in url

    async def get_metadata(self, url: str) -> MediaMetadata:
        # Call the upstream API using self.api_key / self.base_url / self.timeout.
        return MediaMetadata(title="...", duration=12.0, formats=[])

    async def get_formats(self, url: str) -> list[MediaFormat]:
        return (await self.get_metadata(url)).formats

    async def download(self, url: str, dest_dir: str) -> DownloadResult:
        # LEGAL: if the upstream reports the content is private / requires
        # login, refuse — never work around it:
        #   raise ProviderException(DownloadError.PRIVATE_CONTENT)
        # Enforce size/duration guards, download into dest_dir, then:
        return DownloadResult(
            file_path=f"{dest_dir}/video.mp4",
            file_name="video.mp4",
            file_size=1024,
            file_type="video",  # video | audio | photo | document
        )

    async def get_balance(self) -> dict:
        return {"supported": False}  # or {"supported": True, "balance": ...}

    async def health_check(self) -> bool:
        return True
```

**2.** Add one line to `REGISTRY` in `apps/api/app/providers/manager.py`:

```python
REGISTRY: dict[str, type[BaseProvider]] = {
    "ytdlp": YtDlpProvider,
    "apify": ApifyInstagramProvider,
    "your_provider": YourProvider,   # <-- add this
}
```

**3.** Create the provider row from the admin panel (Providers page — or seed data): set **provider type** to the registry key (`your_provider`), pick the **platform**, set a **priority** (lower = tried first), and paste the **API key** (encrypted automatically). Use the panel's *Test* and *Balance* buttons (`POST /api/admin/providers/{id}/test`, `GET /api/admin/providers/{id}/balance` — see [API.md](API.md)) to verify it works.

That's all — no other code changes. The worker picks the new provider up on the next download for that platform.

See also: [API.md](API.md) for the provider admin endpoints · [ADMIN.md](ADMIN.md) for the panel.
