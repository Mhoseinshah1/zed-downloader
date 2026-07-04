"""HTTP client for the backend internal API (/api/internal/*).

A single shared ``httpx.AsyncClient`` authenticates every request with the
``X-Internal-Secret`` header. All functions return parsed JSON on success and
``None`` on network / server errors so handlers can show
``errors.api_unreachable`` instead of crashing.
"""

import logging
from typing import Any

import httpx

from bot.config import get_settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def get_client() -> httpx.AsyncClient:
    """Return the shared AsyncClient, creating it lazily on first use."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = httpx.AsyncClient(
            base_url=settings.api_base_url,
            headers={"X-Internal-Secret": settings.telegram_webhook_secret},
            timeout=_TIMEOUT,
        )
    return _client


async def close_client() -> None:
    """Close the shared client (registered as a dispatcher shutdown hook)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _clean(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop None values so optional fields are omitted, not sent as null."""
    return {key: value for key, value in payload.items() if value is not None}


async def _post(
    path: str, payload: dict[str, Any], *, accept_4xx: bool = False
) -> dict[str, Any] | None:
    try:
        response = await get_client().post(path, json=payload)
    except httpx.HTTPError as exc:
        logger.warning("Internal API POST %s failed: %s", path, exc)
        return None
    if response.status_code >= 500 or (response.status_code >= 400 and not accept_4xx):
        logger.warning("Internal API POST %s returned %s", path, response.status_code)
        return None
    try:
        return response.json()
    except ValueError:
        logger.warning("Internal API POST %s returned non-JSON body", path)
        return None


async def _get(path: str) -> dict[str, Any] | None:
    try:
        response = await get_client().get(path)
    except httpx.HTTPError as exc:
        logger.warning("Internal API GET %s failed: %s", path, exc)
        return None
    if response.status_code >= 400:
        logger.warning("Internal API GET %s returned %s", path, response.status_code)
        return None
    try:
        return response.json()
    except ValueError:
        logger.warning("Internal API GET %s returned non-JSON body", path)
        return None


async def upsert_user(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    language: str | None = None,
) -> dict[str, Any] | None:
    """POST /api/internal/users/upsert -> {id, telegram_id, language, is_blocked}."""
    return await _post(
        "/api/internal/users/upsert",
        _clean(
            {
                "telegram_id": telegram_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "language": language,
            }
        ),
    )


async def set_language(telegram_id: int, language: str) -> dict[str, Any] | None:
    """POST /api/internal/users/{telegram_id}/language -> {ok: true}."""
    return await _post(
        f"/api/internal/users/{telegram_id}/language", {"language": language}
    )


async def upsert_group(
    telegram_chat_id: int,
    title: str | None = None,
    username: str | None = None,
) -> dict[str, Any] | None:
    """POST /api/internal/groups/upsert -> {id, telegram_chat_id, is_enabled}."""
    return await _post(
        "/api/internal/groups/upsert",
        _clean(
            {
                "telegram_chat_id": telegram_chat_id,
                "title": title,
                "username": username,
            }
        ),
    )


async def request_download(
    telegram_id: int,
    url: str,
    chat_id: int | None = None,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    language: str | None = None,
) -> dict[str, Any] | None:
    """POST /api/internal/download/request.

    Returns the contract body: {status: "queued"|"denied"|"error", ...}.
    ``chat_id`` is the group chat id when the request comes from a group and
    is omitted for private chats.
    """
    # NOTE: accept_4xx=True in case the backend signals "denied" responses
    # with a 4xx status code; the body still carries the contract fields.
    return await _post(
        "/api/internal/download/request",
        _clean(
            {
                "telegram_id": telegram_id,
                "chat_id": chat_id,
                "url": url,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "language": language,
            }
        ),
        accept_4xx=True,
    )


async def get_plans(scope: str = "user") -> list[dict[str, Any]] | None:
    """GET /api/internal/plans?scope=user|group -> list of plan dicts, or None.

    ``scope`` is ``"user"`` for private-chat (user) plans and ``"group"`` for
    group-chat plans; the backend returns the plans relevant to that scope.
    """
    body = await _get(f"/api/internal/plans?scope={scope}")
    if body is None:
        return None
    return body.get("plans", [])


async def get_forced_channels() -> list[dict[str, Any]] | None:
    """GET /api/internal/forced-join -> list of channel dicts, or None on error."""
    body = await _get("/api/internal/forced-join")
    if body is None:
        return None
    return body.get("channels", [])


async def create_payment(
    telegram_id: int,
    plan_id: int,
    gateway: str = "zarinpal",
    chat_id: int | None = None,
) -> dict[str, Any] | None:
    """POST /api/internal/payments/create -> {payment_id, payment_url, authority}.

    ``chat_id`` is the negative group id and is REQUIRED for group-scope plans;
    it is omitted for user-scope plans in private chats.
    """
    return await _post(
        "/api/internal/payments/create",
        _clean(
            {
                "telegram_id": telegram_id,
                "plan_id": plan_id,
                "gateway": gateway,
                "chat_id": chat_id,
            }
        ),
    )


async def get_texts() -> dict[str, Any] | None:
    """GET /api/internal/texts -> {lang: {key: value}} overlay, or None on error.

    The panel-edited texts overlay the bundled i18n JSON at startup.
    """
    body = await _get("/api/internal/texts")
    if body is None:
        return None
    return body.get("texts", {})
