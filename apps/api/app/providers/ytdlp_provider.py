"""yt-dlp based provider for public content on YouTube/TikTok/Twitter/etc.

PUBLIC CONTENT ONLY: this provider deliberately configures NO cookie file,
NO username/password, NO netrc and no other authentication option. Anything
yt-dlp cannot fetch anonymously is rejected with PRIVATE_CONTENT.

yt-dlp itself is synchronous, so every call runs in a worker thread via
asyncio.to_thread. The library is imported lazily so the API process stays
importable in environments where yt-dlp is not installed (e.g. CI smoke
tests); only the worker actually exercises it.
"""
import asyncio
import os

from app.config import get_settings
from app.providers.base import (
    BaseProvider,
    DownloadError,
    DownloadResult,
    MediaFormat,
    MediaMetadata,
    ProviderException,
)

# Substring -> error-code mapping applied to lowercased yt-dlp error messages.
# Order matters: first match wins, most specific patterns first.
_ERROR_PATTERNS: list[tuple[str, DownloadError]] = [
    ("private", DownloadError.PRIVATE_CONTENT),
    ("login required", DownloadError.PRIVATE_CONTENT),
    ("log in", DownloadError.PRIVATE_CONTENT),
    ("sign in", DownloadError.PRIVATE_CONTENT),
    ("authentication", DownloadError.PRIVATE_CONTENT),
    ("members-only", DownloadError.PRIVATE_CONTENT),
    ("age-restricted", DownloadError.PRIVATE_CONTENT),
    ("unsupported url", DownloadError.UNSUPPORTED_URL),
    ("is not a valid url", DownloadError.UNSUPPORTED_URL),
    ("http error 404", DownloadError.NOT_FOUND),
    ("not found", DownloadError.NOT_FOUND),
    ("does not exist", DownloadError.NOT_FOUND),
    ("no longer available", DownloadError.NOT_FOUND),
    ("has been removed", DownloadError.NOT_FOUND),
    ("unavailable", DownloadError.NOT_FOUND),
    ("http error 429", DownloadError.RATE_LIMITED),
    ("too many requests", DownloadError.RATE_LIMITED),
    ("rate limit", DownloadError.RATE_LIMITED),
    ("max-filesize", DownloadError.FILE_TOO_LARGE),
    ("file is larger", DownloadError.FILE_TOO_LARGE),
    ("timed out", DownloadError.PROVIDER_DOWN),
    ("timeout", DownloadError.PROVIDER_DOWN),
    ("connection", DownloadError.PROVIDER_DOWN),
    ("network", DownloadError.PROVIDER_DOWN),
    ("temporarily", DownloadError.PROVIDER_DOWN),
    ("http error 5", DownloadError.PROVIDER_DOWN),
]


def _map_error(exc: Exception) -> ProviderException:
    msg = str(exc)
    lowered = msg.lower()
    for needle, code in _ERROR_PATTERNS:
        if needle in lowered:
            return ProviderException(code, msg[:500])
    return ProviderException(DownloadError.UNKNOWN_ERROR, msg[:500])


class YtDlpProvider(BaseProvider):
    provider_type = "ytdlp"

    def _base_opts(self) -> dict:
        settings = get_settings()
        return {
            # Single item only — never expand playlists/channels.
            "noplaylist": True,
            "playlist_items": "1",
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": True,
            "socket_timeout": 30,
            "retries": 2,
            "max_filesize": settings.max_file_size_bytes,
            # NOTE: deliberately no cookiefile / username / password / netrc:
            # public content only (see providers/base.py docstring).
        }

    def validate_url(self, url: str) -> bool:
        return url.startswith(("http://", "https://"))

    # --- blocking helpers (run inside asyncio.to_thread) ----------------------

    def _extract_info(self, url: str) -> dict:
        import yt_dlp  # lazy import, see module docstring

        opts = self._base_opts()
        opts["skip_download"] = True
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:  # yt_dlp raises many error types; map them all
            raise _map_error(exc) from exc
        if info is None:
            raise ProviderException(DownloadError.NOT_FOUND, "no media found at URL")
        if info.get("_type") == "playlist":
            entries = info.get("entries") or []
            if not entries:
                raise ProviderException(DownloadError.NOT_FOUND, "empty playlist result")
            info = entries[0]
        return info

    def _do_download(self, url: str, dest_dir: str) -> dict:
        import yt_dlp  # lazy import

        opts = self._base_opts()
        opts.update(
            {
                "outtmpl": os.path.join(dest_dir, "%(id)s.%(ext)s"),
                # Best video+audio merged to mp4 (ffmpeg is in the image);
                # falls back to best single file.
                "format": "bv*+ba/b",
                "merge_output_format": "mp4",
            }
        )
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as exc:
            raise _map_error(exc) from exc
        if info is None:
            raise ProviderException(DownloadError.NOT_FOUND, "no media found at URL")
        return info

    @staticmethod
    def _result_path(info: dict) -> str:
        requested = info.get("requested_downloads") or []
        if requested and requested[0].get("filepath"):
            return requested[0]["filepath"]
        # Fallback for older yt-dlp result shapes.
        path = info.get("filepath") or info.get("_filename")
        if not path:
            raise ProviderException(DownloadError.UNKNOWN_ERROR, "downloaded file path missing")
        return path

    @staticmethod
    def _file_type(info: dict, ext: str) -> str:
        if ext in ("jpg", "jpeg", "png", "webp"):
            return "photo"
        if info.get("vcodec") not in (None, "none"):
            return "video"
        if info.get("acodec") not in (None, "none"):
            return "audio"
        if ext in ("mp4", "mkv", "webm", "mov"):
            return "video"
        if ext in ("mp3", "m4a", "ogg", "opus", "wav"):
            return "audio"
        return "document"

    # --- BaseProvider API ------------------------------------------------------

    async def get_metadata(self, url: str) -> MediaMetadata:
        info = await asyncio.to_thread(self._extract_info, url)
        return MediaMetadata(
            title=info.get("title"),
            duration=info.get("duration"),
            uploader=info.get("uploader") or info.get("channel"),
            thumbnail=info.get("thumbnail"),
            formats=self._formats_from_info(info),
        )

    async def get_formats(self, url: str) -> list[MediaFormat]:
        return (await self.get_metadata(url)).formats

    @staticmethod
    def _formats_from_info(info: dict) -> list[MediaFormat]:
        formats = []
        for f in info.get("formats") or []:
            formats.append(
                MediaFormat(
                    format_id=str(f.get("format_id")),
                    ext=f.get("ext") or "",
                    resolution=f.get("resolution"),
                    filesize=f.get("filesize") or f.get("filesize_approx"),
                    note=f.get("format_note"),
                )
            )
        return formats

    async def download(self, url: str, dest_dir: str) -> DownloadResult:
        settings = get_settings()

        # Phase 1: metadata only — reject too-long/too-large content before
        # spending bandwidth on it.
        info = await asyncio.to_thread(self._extract_info, url)
        duration = info.get("duration")
        if duration and duration > settings.MAX_DURATION_SECONDS:
            raise ProviderException(
                DownloadError.DURATION_TOO_LONG,
                f"duration {int(duration)}s exceeds limit {settings.MAX_DURATION_SECONDS}s",
            )
        estimated = info.get("filesize") or info.get("filesize_approx")
        if estimated and estimated > settings.max_file_size_bytes:
            raise ProviderException(
                DownloadError.FILE_TOO_LARGE,
                f"estimated size {estimated} exceeds limit {settings.max_file_size_bytes}",
            )

        # Phase 2: actual download.
        info = await asyncio.to_thread(self._do_download, url, dest_dir)
        path = self._result_path(info)
        if not os.path.exists(path):
            raise ProviderException(DownloadError.UNKNOWN_ERROR, f"expected file missing: {path}")
        size = os.path.getsize(path)
        if size > settings.max_file_size_bytes:
            os.remove(path)
            raise ProviderException(
                DownloadError.FILE_TOO_LARGE,
                f"downloaded size {size} exceeds limit {settings.max_file_size_bytes}",
            )
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        return DownloadResult(
            file_path=path,
            file_name=os.path.basename(path),
            file_size=size,
            file_type=self._file_type(info, ext),
            title=info.get("title"),
            duration=info.get("duration"),
            width=info.get("width"),
            height=info.get("height"),
        )

    async def get_balance(self) -> dict:
        return {"supported": False, "note": "yt-dlp is free — no upstream balance"}

    async def health_check(self) -> bool:
        try:
            import yt_dlp  # noqa: F401  lazy import
            return True
        except ImportError:
            return False
