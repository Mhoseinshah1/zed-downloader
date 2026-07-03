"""Apify-based provider for PUBLIC Instagram posts/reels.

Uses the run-sync-get-dataset-items endpoint of the Instagram scraper actor,
then streams the resolved media URL to disk with a hard size cap.

PUBLIC CONTENT ONLY: private/restricted profiles are rejected with
PRIVATE_CONTENT — no session cookies or logins, ever.
"""
import os
import re
import urllib.parse

import httpx

from app.config import get_settings
from app.providers.base import (
    BaseProvider,
    DownloadError,
    DownloadResult,
    MediaFormat,
    MediaMetadata,
    ProviderException,
)

_IG_URL_RE = re.compile(r"instagram\.com/(?:[^/]+/)?(p|reel|reels|tv)/([A-Za-z0-9_-]+)", re.IGNORECASE)


class ApifyInstagramProvider(BaseProvider):
    provider_type = "apify"

    DEFAULT_BASE_URL = "https://api.apify.com"
    # Overridable per provider row via settings JSON: {"actor": "..."}
    DEFAULT_ACTOR = "apify~instagram-scraper"

    @property
    def _api_base(self) -> str:
        return (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")

    @property
    def _actor(self) -> str:
        return self.settings.get("actor", self.DEFAULT_ACTOR)

    def _require_key(self) -> str:
        if not self.api_key:
            # Recoverable: the manager may fall back to another provider.
            raise ProviderException(DownloadError.PROVIDER_DOWN, "Apify API key is not configured")
        return self.api_key

    def validate_url(self, url: str) -> bool:
        return bool(_IG_URL_RE.search(url))

    # --- Apify API -------------------------------------------------------------

    async def _run_actor(self, url: str) -> dict:
        token = self._require_key()
        endpoint = f"{self._api_base}/v2/acts/{self._actor}/run-sync-get-dataset-items"
        payload = {
            "directUrls": [url],
            "resultsType": "posts",
            "resultsLimit": 1,
            "addParentData": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(endpoint, params={"token": token}, json=payload)
        except httpx.HTTPError as exc:
            raise ProviderException(DownloadError.PROVIDER_DOWN, f"apify unreachable: {exc}") from exc

        if resp.status_code == 429:
            raise ProviderException(DownloadError.RATE_LIMITED, "apify rate limit hit")
        if resp.status_code in (401, 403):
            raise ProviderException(DownloadError.PROVIDER_DOWN, "apify token rejected")
        if resp.status_code >= 500:
            raise ProviderException(DownloadError.PROVIDER_DOWN, f"apify 5xx: {resp.status_code}")
        if resp.status_code >= 400:
            raise ProviderException(DownloadError.UNKNOWN_ERROR, f"apify {resp.status_code}: {resp.text[:300]}")

        items = resp.json()
        if not isinstance(items, list) or not items:
            raise ProviderException(DownloadError.NOT_FOUND, "no items returned for URL")
        item = items[0]

        error = str(item.get("error") or item.get("errorDescription") or "").lower()
        if "private" in error or "restricted" in error:
            raise ProviderException(DownloadError.PRIVATE_CONTENT, "instagram content is private")
        if "not found" in error or "page_not_found" in error:
            raise ProviderException(DownloadError.NOT_FOUND, "instagram content not found")
        if error:
            raise ProviderException(DownloadError.UNKNOWN_ERROR, f"apify item error: {error[:200]}")
        return item

    @staticmethod
    def _pick_media(item: dict) -> tuple[str, str]:
        """Return (media_url, file_type) for the best media in the item."""
        video_url = item.get("videoUrl")
        if video_url:
            return video_url, "video"
        # Carousel: first child with media (single-item MVP; NOTE: v2 could
        # send whole albums).
        for child in item.get("childPosts") or []:
            if child.get("videoUrl"):
                return child["videoUrl"], "video"
            if child.get("displayUrl"):
                return child["displayUrl"], "photo"
        display_url = item.get("displayUrl")
        if display_url:
            return display_url, "photo"
        raise ProviderException(DownloadError.NOT_FOUND, "no media URL in apify result")

    # --- BaseProvider API ------------------------------------------------------

    async def get_metadata(self, url: str) -> MediaMetadata:
        item = await self._run_actor(url)
        media_url, file_type = self._pick_media(item)
        ext = self._ext_from_url(media_url, file_type)
        return MediaMetadata(
            title=(item.get("caption") or "")[:200] or None,
            duration=item.get("videoDuration"),
            uploader=item.get("ownerUsername"),
            thumbnail=item.get("displayUrl"),
            formats=[MediaFormat(format_id="default", ext=ext, note=file_type)],
        )

    async def get_formats(self, url: str) -> list[MediaFormat]:
        return (await self.get_metadata(url)).formats

    @staticmethod
    def _ext_from_url(media_url: str, file_type: str) -> str:
        path = urllib.parse.urlparse(media_url).path
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        if ext:
            return ext
        return "mp4" if file_type == "video" else "jpg"

    async def download(self, url: str, dest_dir: str) -> DownloadResult:
        settings = get_settings()
        item = await self._run_actor(url)

        duration = item.get("videoDuration")
        if duration and duration > settings.MAX_DURATION_SECONDS:
            raise ProviderException(
                DownloadError.DURATION_TOO_LONG,
                f"duration {int(duration)}s exceeds limit {settings.MAX_DURATION_SECONDS}s",
            )

        media_url, file_type = self._pick_media(item)
        ext = self._ext_from_url(media_url, file_type)
        short_code = item.get("shortCode") or "media"
        file_name = f"instagram_{short_code}.{ext}"
        file_path = os.path.join(dest_dir, file_name)

        cap = settings.max_file_size_bytes
        written = 0
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                async with client.stream("GET", media_url) as resp:
                    if resp.status_code >= 400:
                        raise ProviderException(
                            DownloadError.PROVIDER_DOWN, f"media fetch failed: {resp.status_code}"
                        )
                    declared = resp.headers.get("content-length")
                    if declared and int(declared) > cap:
                        raise ProviderException(
                            DownloadError.FILE_TOO_LARGE, f"declared size {declared} exceeds cap"
                        )
                    with open(file_path, "wb") as fh:
                        async for chunk in resp.aiter_bytes():
                            written += len(chunk)
                            if written > cap:
                                # Enforce the cap mid-stream, not just via headers.
                                raise ProviderException(
                                    DownloadError.FILE_TOO_LARGE, f"stream exceeded cap {cap}"
                                )
                            fh.write(chunk)
        except ProviderException:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise
        except httpx.HTTPError as exc:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise ProviderException(DownloadError.PROVIDER_DOWN, f"media fetch error: {exc}") from exc

        return DownloadResult(
            file_path=file_path,
            file_name=file_name,
            file_size=written,
            file_type=file_type,
            title=(item.get("caption") or "")[:200] or None,
            duration=duration,
            width=item.get("dimensionsWidth"),
            height=item.get("dimensionsHeight"),
        )

    async def get_balance(self) -> dict:
        token = self._require_key()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{self._api_base}/v2/users/me", params={"token": token})
        except httpx.HTTPError as exc:
            return {"supported": True, "ok": False, "error": str(exc)}
        if resp.status_code != 200:
            return {"supported": True, "ok": False, "error": f"status {resp.status_code}"}
        data = resp.json().get("data", {})
        # Only surface non-sensitive account fields.
        return {
            "supported": True,
            "ok": True,
            "username": data.get("username"),
            "plan": (data.get("plan") or {}).get("id"),
            "monthly_usage_cycle": data.get("currentBillingPeriod"),
        }

    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{self._api_base}/v2/users/me", params={"token": self.api_key})
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
