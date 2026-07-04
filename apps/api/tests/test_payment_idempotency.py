"""Payment orchestration idempotency + safety (app.services.payment_service)."""
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Group, Payment, Plan, Subscription, User
from app.payments.base import (
    BasePaymentProvider,
    PaymentGatewayError,
    PaymentInit,
    PaymentVerdict,
)
from app.services import payment_service as ps
from app.services.payment_service import create_payment_record, verify_and_activate


class StubGateway(BasePaymentProvider):
    """In-memory gateway. Class attributes are reset by the fixture per test."""

    gateway_name = "stub"
    verify_ok = True
    ref_id = "REF-1"
    raise_on_verify = False

    async def create_payment(self, *, amount, currency, description, callback_url) -> PaymentInit:
        return PaymentInit(authority="AUTH-STUB", payment_url="http://pay/AUTH-STUB")

    async def verify_payment(self, *, authority, amount, currency) -> PaymentVerdict:
        if StubGateway.raise_on_verify:
            raise PaymentGatewayError("gateway unreachable")
        if not StubGateway.verify_ok:
            return PaymentVerdict(ok=False, message="rejected")
        return PaymentVerdict(ok=True, ref_id=StubGateway.ref_id, message="ok")


@pytest.fixture
def stub_gateway():
    StubGateway.verify_ok = True
    StubGateway.ref_id = "REF-1"
    StubGateway.raise_on_verify = False
    ps.GATEWAYS["stub"] = StubGateway
    try:
        yield StubGateway
    finally:
        ps.GATEWAYS.pop("stub", None)


# --- factories -------------------------------------------------------------

async def _user(session, telegram_id=7001):
    u = User(telegram_id=telegram_id)
    session.add(u)
    await session.flush()
    return u


async def _plan(session, *, scope="user", name="Plan"):
    p = Plan(
        name=name,
        price=Decimal("5000"),
        currency="IRT",
        duration_days=30,
        download_limit=100,
        scope=scope,
        is_active=True,
    )
    session.add(p)
    await session.flush()
    return p


async def _group(session, chat_id=-9001):
    g = Group(telegram_chat_id=chat_id)
    session.add(g)
    await session.flush()
    return g


async def _count(session, model):
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


# --- tests -----------------------------------------------------------------

async def test_double_verify_is_idempotent(session, stub_gateway):
    user = await _user(session)
    plan = await _plan(session)
    payment, _url = await create_payment_record(
        session, user=user, plan=plan, gateway_name="stub"
    )
    authority = payment.authority

    first = await verify_and_activate(session, authority=authority)
    assert first.ok is True
    assert first.status == "success"

    second = await verify_and_activate(session, authority=authority)
    assert second.ok is True
    assert second.status == "already_verified"

    # Exactly one subscription despite verifying twice.
    assert await _count(session, Subscription) == 1
    assert await _count(session, Payment) == 1


async def test_transaction_id_unique_constraint(session, stub_gateway):
    user = await _user(session)
    plan = await _plan(session)
    session.add(
        Payment(user_id=user.id, plan_id=plan.id, gateway="stub", amount=Decimal("1"),
                currency="IRT", status="success", transaction_id="DUP")
    )
    session.add(
        Payment(user_id=user.id, plan_id=plan.id, gateway="stub", amount=Decimal("1"),
                currency="IRT", status="success", transaction_id="DUP")
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_gateway_nok_marks_failed_and_stays_failed(session, stub_gateway):
    user = await _user(session)
    plan = await _plan(session)
    payment, _url = await create_payment_record(
        session, user=user, plan=plan, gateway_name="stub"
    )
    pid = payment.id
    authority = payment.authority

    # User cancelled / gateway said NOK -> failed without any verify call.
    out = await verify_and_activate(session, authority=authority, gateway_status="NOK")
    assert out.ok is False
    assert out.status == "failed"
    assert (await session.get(Payment, pid)).status == "failed"

    # A subsequent (even OK) callback must not resurrect it.
    out2 = await verify_and_activate(session, authority=authority, gateway_status="OK")
    assert out2.ok is False
    assert out2.status == "failed"
    assert (await session.get(Payment, pid)).status == "failed"
    assert await _count(session, Subscription) == 0


async def test_group_scope_binds_subscription_to_group(session, stub_gateway):
    user = await _user(session)
    group = await _group(session)
    plan = await _plan(session, scope="group", name="Group Plan")

    payment, _url = await create_payment_record(
        session, user=user, plan=plan, gateway_name="stub", group=group
    )
    assert payment.group_id == group.id

    out = await verify_and_activate(session, authority=payment.authority)
    assert out.ok is True
    assert out.status == "success"

    sub = (await session.execute(select(Subscription))).scalar_one()
    assert sub.group_id == group.id
    assert sub.user_id is None


async def test_scope_flip_backstop_blocks_activation(session, stub_gateway):
    """A user-scope payment whose plan is flipped to group-scope after the
    payment was created must NOT produce an orphan subscription: activation
    is refused, the transaction rolls back, the payment stays pending."""
    user = await _user(session)
    plan = await _plan(session, scope="user")

    payment, _url = await create_payment_record(
        session, user=user, plan=plan, gateway_name="stub"
    )
    pid = payment.id
    authority = payment.authority
    assert payment.group_id is None  # no group recorded

    # Flip the plan to group scope AFTER the payment (and no group on payment).
    plan.scope = "group"
    await session.commit()

    out = await verify_and_activate(session, authority=authority)
    assert out.ok is False
    assert out.status == "activation_blocked"

    # No orphan subscription, and the payment is left pending for manual refund.
    assert await _count(session, Subscription) == 0
    assert (await session.get(Payment, pid)).status == "pending"


async def test_verify_unknown_authority_returns_not_found(session, stub_gateway):
    out = await verify_and_activate(session, authority="does-not-exist")
    assert out.ok is False
    assert out.status == "not_found"
