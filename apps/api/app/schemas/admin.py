"""Schemas for the admin-panel endpoints."""
import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# --- Users / groups ---------------------------------------------------------

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language: str
    is_blocked: bool
    total_downloads: int
    created_at: dt.datetime


class UserPatch(BaseModel):
    language: str | None = None
    is_blocked: bool | None = None


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_chat_id: int
    title: str | None = None
    username: str | None = None
    is_enabled: bool
    daily_limit: int | None = None
    downloads_today: int
    total_downloads: int
    created_at: dt.datetime


class GroupPatch(BaseModel):
    title: str | None = None
    is_enabled: bool | None = None
    daily_limit: int | None = None


# --- Plans / payments ---------------------------------------------------------

class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    price: Decimal
    currency: str
    duration_days: int
    download_limit: int
    scope: str
    is_active: bool
    sort_order: int


class PlanIn(BaseModel):
    name: str
    description: str | None = None
    price: Decimal
    currency: str = "IRT"
    duration_days: int
    download_limit: int = 0
    scope: str = "user"
    is_active: bool = True
    sort_order: int = 0


class PlanPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    duration_days: int | None = None
    download_limit: int | None = None
    scope: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    plan_id: int
    gateway: str
    amount: Decimal
    currency: str
    status: str
    transaction_id: str | None = None
    authority: str | None = None
    paid_at: dt.datetime | None = None
    created_at: dt.datetime


# --- Platforms / providers -----------------------------------------------------

class PlatformOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    url_regex: str
    is_active: bool
    sort_order: int


class PlatformIn(BaseModel):
    name: str
    slug: str
    url_regex: str
    is_active: bool = True
    sort_order: int = 0


class PlatformPatch(BaseModel):
    name: str | None = None
    slug: str | None = None
    url_regex: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class ProviderOut(BaseModel):
    # Built manually in routes: never exposes the (encrypted) API key, only
    # whether one is stored.
    id: int
    name: str
    slug: str
    platform_id: int
    provider_type: str
    has_api_key: bool
    base_url: str | None = None
    priority: int
    timeout: int
    settings: dict
    is_active: bool


class ProviderIn(BaseModel):
    name: str
    slug: str
    platform_id: int
    provider_type: str
    api_key: str | None = None  # plaintext in transit, Fernet-encrypted at rest
    base_url: str | None = None
    priority: int = 100
    timeout: int = 300
    settings: dict = {}
    is_active: bool = True


class ProviderPatch(BaseModel):
    name: str | None = None
    slug: str | None = None
    platform_id: int | None = None
    provider_type: str | None = None
    # None = leave unchanged; "" = clear the stored key; other = replace.
    api_key: str | None = None
    base_url: str | None = None
    priority: int | None = None
    timeout: int | None = None
    settings: dict | None = None
    is_active: bool | None = None
