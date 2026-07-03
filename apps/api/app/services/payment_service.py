"""Payment orchestration — THE money core. Read before touching.

Money-safety invariants enforced here:
1. activate_subscription() is the ONLY place a subscription is ever
   created/activated, and it is only called after a verified payment.
2. Verification is idempotent: payments.transaction_id has a DB-level UNIQUE
   constraint, and verify_and_activate() branches on the payment's current
   status, so re-verifying a successful payment never double-credits.
3. verify_and_activate() takes a row lock (SELECT ... FOR UPDATE) on the
   payment row so concurrent callbacks serialize.
"""
import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import utcnow
from app.models import Payment, Plan, Subscription, User
from app.payments.base import BasePaymentProvider, PaymentGatewayError
from app.payments.zarinpal import ZarinpalGateway

GATEWAYS: dict[str, type[BasePaymentProvider]] = {
    "zarinpal": ZarinpalGateway,
    # To add a gateway: write the class in app/payments/, add one line here,
    # and add its callback route in app/routes/payments.py.
}


def build_gateway(name: str) -> BasePaymentProvider:
    cls = GATEWAYS.get(name)
    if cls is None:
        raise PaymentGatewayError(f"unknown payment gateway: {name}")
    return cls()


async def create_payment_record(
    session: AsyncSession, *, user: User, plan: Plan, gateway_name: str
) -> tuple[Payment, str]:
    """Create a pending payment row + a gateway payment session.
    Returns (payment, redirect_url). Commits on success."""
    gateway = build_gateway(gateway_name)
    settings = get_settings()

    payment = Payment(
        user_id=user.id,
        plan_id=plan.id,
        gateway=gateway_name,
        amount=plan.price,
        currency=plan.currency,
        status="pending",
        description=f"Plan '{plan.name}' for telegram user {user.telegram_id}",
    )
    session.add(payment)
    await session.flush()  # assign payment.id before talking to the gateway

    callback_url = f"{settings.payment_callback_base}/payments/{gateway_name}/callback"
    init = await gateway.create_payment(
        amount=plan.price,
        currency=plan.currency,
        description=payment.description or "",
        callback_url=callback_url,
    )
    payment.authority = init.authority
    await session.commit()
    return payment, init.payment_url


async def activate_subscription(session: AsyncSession, payment: Payment) -> Subscription:
    """THE single subscription-activation point (invariant #1).

    Caller must hold the payment row lock and must have just verified the
    payment. Flushes but does not commit — the caller owns the transaction.
    """
    plan = await session.get(Plan, payment.plan_id)
    if plan is None:  # defensive: FK guarantees this in practice
        raise PaymentGatewayError(f"payment {payment.id} references missing plan {payment.plan_id}")
    if plan.scope != "user":
        # Backstop for the guard in the payment-creation route (closes the
        # window where an admin flips a plan's scope mid-payment). Raising
        # here rolls the transaction back, so the payment stays visible as
        # pending for manual refund instead of silently crediting nobody.
        # NOTE: group-scope purchase (setting group_id) is a v2 seam.
        raise PaymentGatewayError(
            f"plan {plan.id} has scope '{plan.scope}' — only user-scope plans are activatable"
        )
    now = utcnow()
    subscription = Subscription(
        user_id=payment.user_id,
        group_id=None,
        plan_id=plan.id,
        starts_at=now,
        expires_at=now + dt.timedelta(days=plan.duration_days),
        downloads_used=0,
        is_active=True,
        payment_id=payment.id,
    )
    session.add(subscription)
    await session.flush()
    return subscription


@dataclass
class VerifyOutcome:
    ok: bool
    status: str  # success | already_verified | failed | not_found | gateway_error
    payment: Payment | None = None
    ref_id: str | None = None
    message: str = ""


async def verify_and_activate(
    session: AsyncSession, *, authority: str, gateway_status: str | None = None
) -> VerifyOutcome:
    """Verify a gateway callback and activate the subscription exactly once.

    Safe to call any number of times for the same authority (invariant #2).
    """
    # Row lock so two concurrent callbacks for the same payment serialize
    # (invariant #3). On SQLite FOR UPDATE is a no-op, which is acceptable —
    # production runs on PostgreSQL.
    result = await session.execute(
        select(Payment).where(Payment.authority == authority).with_for_update()
    )
    payment = result.scalar_one_or_none()
    if payment is None:
        return VerifyOutcome(False, "not_found", message="no payment for this authority")

    # Branch on current status while holding the lock.
    if payment.status == "success":
        # Already credited — idempotent no-op, never credit twice.
        return VerifyOutcome(True, "already_verified", payment, payment.transaction_id)
    if payment.status == "failed":
        return VerifyOutcome(False, "failed", payment, message="payment already marked failed")

    # status == "pending" from here on.
    if gateway_status is not None and gateway_status.upper() != "OK":
        # User cancelled / gateway reported failure — no server-side verify call needed.
        payment.status = "failed"
        await session.commit()
        return VerifyOutcome(False, "failed", payment, message="gateway reported failure")

    gateway = build_gateway(payment.gateway)
    try:
        verdict = await gateway.verify_payment(
            authority=authority, amount=payment.amount, currency=payment.currency
        )
    except PaymentGatewayError as exc:
        # Gateway unreachable: keep the payment pending so a later callback /
        # retry can still verify it. Do NOT mark failed here.
        await session.rollback()
        return VerifyOutcome(False, "gateway_error", message=str(exc))

    if not verdict.ok:
        payment.status = "failed"
        await session.commit()
        return VerifyOutcome(False, "failed", payment, message=verdict.message)

    payment.status = "success"
    payment.transaction_id = str(verdict.ref_id)
    payment.paid_at = utcnow()
    try:
        await activate_subscription(session, payment)
    except PaymentGatewayError as exc:
        # Activation refused (e.g. plan scope changed mid-payment). Roll
        # everything back: the payment stays pending and visible for manual
        # refund — the user paid but must never be silently mis-credited.
        await session.rollback()
        return VerifyOutcome(False, "activation_blocked", message=str(exc))
    try:
        await session.commit()
    except IntegrityError:
        # UNIQUE(transaction_id) tripped: another process credited this exact
        # gateway transaction concurrently. Roll back our duplicate — nothing
        # is double-credited (invariant #2, DB-enforced backstop).
        await session.rollback()
        return VerifyOutcome(True, "already_verified", ref_id=str(verdict.ref_id))
    return VerifyOutcome(True, "success", payment, str(verdict.ref_id))
