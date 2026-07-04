"""Schemas for the bot -> api internal endpoints."""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class UserUpsertIn(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language: str | None = None


class UserInternalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    language: str
    is_blocked: bool


class LanguageIn(BaseModel):
    language: str


class GroupUpsertIn(BaseModel):
    telegram_chat_id: int
    title: str | None = None
    username: str | None = None


class GroupInternalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_chat_id: int
    is_enabled: bool


class DownloadRequestIn(BaseModel):
    telegram_id: int
    url: str
    # Group chat id when the message came from a group; None in private chats.
    chat_id: int | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language: str | None = None


class PlanPublicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    price: Decimal
    currency: str
    duration_days: int
    download_limit: int


class PaymentCreateIn(BaseModel):
    telegram_id: int
    plan_id: int
    gateway: str = "zarinpal"
    # Required for group-scope plans: the group chat the subscription is for.
    chat_id: int | None = None
