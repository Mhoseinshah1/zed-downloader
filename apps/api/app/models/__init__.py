"""Re-export every model so `from app import models` registers all tables
on Base.metadata (Alembic autogenerate relies on this)."""
from app.database import Base
from app.models.accounts import Admin, Group, User
from app.models.billing import Payment, Plan, Subscription
from app.models.catalog import (
    Ad,
    BotText,
    ForcedJoinChannel,
    Language,
    Platform,
    Provider,
    Setting,
)
from app.models.content import DownloadRequest, Log, UpdateHistory

__all__ = [
    "Base",
    "Admin",
    "Group",
    "User",
    "Payment",
    "Plan",
    "Subscription",
    "Ad",
    "BotText",
    "ForcedJoinChannel",
    "Language",
    "Platform",
    "Provider",
    "Setting",
    "DownloadRequest",
    "Log",
    "UpdateHistory",
]
