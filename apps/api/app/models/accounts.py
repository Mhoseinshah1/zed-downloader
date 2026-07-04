"""Telegram users, Telegram groups, and panel admins."""
import datetime as dt

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str] = mapped_column(String(8), default="fa", nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    total_downloads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Refreshed on every interaction (Phase 2). Nullable so the additive
    # migration is safe on an existing table.
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Group(TimestampMixin, Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Free-tier quota for the group. None = no group-level daily cap.
    daily_limit: Mapped[int | None] = mapped_column(Integer)
    downloads_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quota_date: Mapped[dt.date | None] = mapped_column(Date)  # day downloads_today refers to
    total_downloads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Admin(TimestampMixin, Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(128))
    # owner | super_admin | support | finance | content_manager
    role: Mapped[str] = mapped_column(String(32), default="support", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class RevokedToken(Base):
    """Blacklist of admin JWT ids (jti) invalidated before their natural
    expiry — e.g. on logout. Checked on every authenticated request and on
    refresh. Rows are purged once past expires_at (housekeeping)."""

    __tablename__ = "revoked_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    admin_id: Mapped[int | None] = mapped_column(Integer, index=True)
    token_type: Mapped[str] = mapped_column(String(16), nullable=False)  # access | refresh
    # When the underlying token would have expired anyway (safe to purge after).
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    revoked_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
