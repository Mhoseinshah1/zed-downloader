"""Provider seam: every downloader implements BaseProvider.

LEGAL SCOPE — providers handle PUBLIC, permitted content only. Anything
that would require authentication (private posts, subscriber-only or
age-gated media) must raise ProviderException(DownloadError.PRIVATE_CONTENT).
Never add cookie files, logins, session tokens or any other bypass.
"""
import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class DownloadError(str, enum.Enum):
    UNSUPPORTED_URL = "unsupported_url"
    PRIVATE_CONTENT = "private_content"
    NOT_FOUND = "not_found"
    PROVIDER_DOWN = "provider_down"
    RATE_LIMITED = "rate_limited"
    FILE_TOO_LARGE = "file_too_large"
    DURATION_TOO_LONG = "duration_too_long"
    UNKNOWN_ERROR = "unknown_error"


# Errors where trying the next provider (by priority) might still succeed.
# Everything else is a property of the content itself, so the manager fails
# fast instead of hammering other providers.
RECOVERABLE_ERRORS = frozenset(
    {DownloadError.PROVIDER_DOWN, DownloadError.RATE_LIMITED, DownloadError.UNKNOWN_ERROR}
)


class ProviderException(Exception):
    def __init__(self, code: DownloadError, message: str = ""):
        self.code = code
        self.message = message or code.value
        super().__init__(self.message)


@dataclass
class MediaFormat:
    format_id: str
    ext: str
    resolution: str | None = None
    filesize: int | None = None
    note: str | None = None


@dataclass
class MediaMetadata:
    title: str | None = None
    duration: float | None = None  # seconds
    uploader: str | None = None
    thumbnail: str | None = None
    formats: list[MediaFormat] = field(default_factory=list)


@dataclass
class DownloadResult:
    file_path: str
    file_name: str
    file_size: int  # bytes
    file_type: str  # video | audio | photo | document
    title: str | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None


class BaseProvider(ABC):
    """Instances are built by providers.manager.build_provider from a DB row."""

    provider_type: str = "base"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 300,
        settings: dict | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.settings = settings or {}

    @abstractmethod
    def validate_url(self, url: str) -> bool:
        """Cheap syntactic check: could this provider handle the URL at all?"""

    @abstractmethod
    async def get_metadata(self, url: str) -> MediaMetadata: ...

    @abstractmethod
    async def get_formats(self, url: str) -> list[MediaFormat]: ...

    @abstractmethod
    async def download(self, url: str, dest_dir: str) -> DownloadResult:
        """Download the media into dest_dir. Must enforce size/duration guards
        and must raise ProviderException(PRIVATE_CONTENT) for private content."""

    async def get_balance(self) -> dict:
        """Remaining credit on the upstream API, when the provider has one."""
        return {"supported": False}

    async def health_check(self) -> bool:
        """True when the provider looks usable right now."""
        return True
