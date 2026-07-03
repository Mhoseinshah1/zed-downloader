"""Plans, subscriptions and payments — the money tables.

Invariants (see project rules):
- payments.transaction_id is UNIQUE at the DB level: the idempotency guard
  that makes double-crediting impossible even under concurrent verification.
- Subscriptions are only ever created by payment_service.activate_subscription.
"""
import datetime as dt
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512))
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="IRT", nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # Downloads allowed during the subscription period. 0 = unlimited.
    download_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scope: Mapped[str] = mapped_column(String(16), default="user", nullable=False)  # user | group
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    starts_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    downloads_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))

    plan: Mapped[Plan] = relationship(lazy="joined")


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    gateway: Mapped[str] = mapped_column(String(32), nullable=False)  # key into GATEWAYS
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="IRT", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)  # pending | success | failed
    # Gateway reference id, set only on verified success. DB-level UNIQUE =
    # the idempotency guard against double-credit.
    transaction_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    authority: Mapped[str | None] = mapped_column(String(128), index=True)  # gateway session/authority token
    description: Mapped[str | None] = mapped_column(String(512))
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    plan: Mapped[Plan] = relationship(lazy="joined")
