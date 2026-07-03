"""Payments: public gateway callback + admin plans CRUD + payments list."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Payment, Plan, User
from app.routes.deps import require_role
from app.schemas.admin import PaymentOut, PlanIn, PlanOut, PlanPatch
from app.services.payment_service import verify_and_activate

admin_router = APIRouter(prefix="/api/admin", tags=["billing"])
public_router = APIRouter(prefix="/payments", tags=["payments-public"])


# --- Admin: plans CRUD --------------------------------------------------------

_plans_guard = Depends(require_role("super_admin", "finance", "content_manager"))


@admin_router.get("/plans", dependencies=[_plans_guard])
async def list_plans(db: AsyncSession = Depends(get_db)) -> dict:
    rows = await db.execute(select(Plan).order_by(Plan.sort_order.asc(), Plan.id.asc()))
    return {"items": [PlanOut.model_validate(p).model_dump(mode="json") for p in rows.scalars()]}


@admin_router.post(
    "/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED, dependencies=[_plans_guard]
)
async def create_plan(body: PlanIn, db: AsyncSession = Depends(get_db)) -> Plan:
    if body.scope not in ("user", "group"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "scope must be 'user' or 'group'")
    plan = Plan(**body.model_dump())
    db.add(plan)
    await db.commit()
    return plan


@admin_router.patch("/plans/{plan_id}", response_model=PlanOut, dependencies=[_plans_guard])
async def patch_plan(plan_id: int, body: PlanPatch, db: AsyncSession = Depends(get_db)) -> Plan:
    plan = await db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "plan not found")
    data = body.model_dump(exclude_unset=True)
    if "scope" in data and data["scope"] not in ("user", "group"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "scope must be 'user' or 'group'")
    for field, value in data.items():
        setattr(plan, field, value)
    await db.commit()
    return plan


@admin_router.delete("/plans/{plan_id}", dependencies=[_plans_guard])
async def delete_plan(plan_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    plan = await db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "plan not found")
    await db.delete(plan)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "plan has subscriptions/payments — set is_active=false instead of deleting",
        )
    return {"ok": True}


# --- Admin: payments list --------------------------------------------------------

@admin_router.get("/payments", dependencies=[Depends(require_role("super_admin", "finance"))])
async def list_payments(
    status_filter: str = Query(default="", alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(Payment, User.telegram_id).join(User, Payment.user_id == User.id)
    if status_filter:
        query = query.where(Payment.status == status_filter)
    total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one())
    rows = await db.execute(
        query.order_by(Payment.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = []
    for payment, telegram_id in rows:
        item = PaymentOut.model_validate(payment).model_dump(mode="json")
        item["user_telegram_id"] = telegram_id
        item["plan_name"] = payment.plan.name if payment.plan else None
        items.append(item)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# --- Public: Zarinpal callback -----------------------------------------------------

_RESULT_PAGE = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_fa}</title>
<style>
  body {{ background:#0f1115; color:#e8eaed; font-family: Tahoma, 'Segoe UI', sans-serif;
         display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; }}
  .card {{ background:#171a21; border-radius:16px; padding:40px 48px; text-align:center;
           max-width:420px; box-shadow:0 8px 30px rgba(0,0,0,.4); }}
  .icon {{ font-size:56px; margin-bottom:16px; }}
  h1 {{ font-size:20px; margin:0 0 8px; }}
  p  {{ color:#9aa0a6; font-size:14px; line-height:1.8; margin:4px 0; }}
  .ref {{ direction:ltr; color:#8ab4f8; font-family:monospace; }}
</style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>{title_fa}</h1>
    <p>{body_fa}</p>
    <p lang="en" dir="ltr">{body_en}</p>
    {ref_html}
    <p>می‌توانید این صفحه را ببندید و به ربات تلگرام برگردید.<br>
       <span lang="en" dir="ltr">You can close this page and return to the Telegram bot.</span></p>
  </div>
</body>
</html>"""


def _render_result(icon: str, title_fa: str, body_fa: str, body_en: str, ref_id: str | None = None) -> str:
    ref_html = f'<p>کد پیگیری / Ref ID: <span class="ref">{ref_id}</span></p>' if ref_id else ""
    return _RESULT_PAGE.format(
        icon=icon, title_fa=title_fa, body_fa=body_fa, body_en=body_en, ref_html=ref_html
    )


@public_router.get("/zarinpal/callback", response_class=HTMLResponse)
async def zarinpal_callback(
    authority: str = Query(default="", alias="Authority"),
    gateway_status: str | None = Query(default=None, alias="Status"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    if not authority:
        return HTMLResponse(
            _render_result("⚠️", "درخواست نامعتبر", "پارامترهای بازگشت ناقص است.", "Missing callback parameters."),
            status_code=400,
        )

    outcome = await verify_and_activate(db, authority=authority, gateway_status=gateway_status)

    if outcome.status in ("success", "already_verified"):
        return HTMLResponse(
            _render_result(
                "✅",
                "پرداخت موفق",
                "اشتراک شما فعال شد. از خرید شما متشکریم!",
                "Payment verified — your subscription is now active.",
                outcome.ref_id,
            )
        )
    if outcome.status == "gateway_error":
        return HTMLResponse(
            _render_result(
                "⏳",
                "در انتظار تأیید",
                "درگاه پرداخت موقتاً پاسخ نمی‌دهد. اگر مبلغ کسر شده، به‌زودی به‌صورت خودکار تأیید می‌شود.",
                "The gateway is temporarily unreachable. If you were charged, verification will be retried.",
            ),
            status_code=502,
        )
    if outcome.status == "not_found":
        return HTMLResponse(
            _render_result("⚠️", "پرداخت یافت نشد", "پرداختی با این شناسه پیدا نشد.", "No payment matches this authority."),
            status_code=404,
        )
    return HTMLResponse(
        _render_result(
            "❌",
            "پرداخت ناموفق",
            "پرداخت انجام نشد یا لغو شد. در صورت کسر مبلغ، طی ۷۲ ساعت بازگشت داده می‌شود.",
            "The payment failed or was cancelled. Any deducted amount is refunded by the gateway.",
        )
    )
