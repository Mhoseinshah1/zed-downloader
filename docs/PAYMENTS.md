# Payments

Subscription plans are sold through the bot and paid via pluggable payment gateways. **Zarinpal** ships in v1; the architecture is a small registry so more gateways (Zibal, Telegram Stars, TON, TRON) can be added in v2 without touching the money core.

## Architecture

| Piece | Where | Role |
|---|---|---|
| `BasePaymentProvider` ABC | `apps/api/app/payments/base.py` | Gateway seam: `create_payment(...) -> PaymentInit`, `verify_payment(...) -> PaymentVerdict` |
| `ZarinpalGateway` | `apps/api/app/payments/zarinpal.py` | Zarinpal v4 REST implementation (sandbox toggle) |
| `GATEWAYS` registry | `apps/api/app/services/payment_service.py` | `{"zarinpal": ZarinpalGateway}` — one line per gateway |
| `payment_service` | `apps/api/app/services/payment_service.py` | **The money core**: creates payment rows, verifies callbacks, activates subscriptions |
| Callback route | `apps/api/app/routes/payments.py` | `GET /payments/zarinpal/callback` (public), renders an HTML result page (see code) |

`create_payment` returns a `PaymentInit(authority, payment_url)`; `verify_payment` returns a `PaymentVerdict(ok, ref_id, message)`. Verification *failures* are normal return values — only "the gateway could not even be reached/understood" raises `PaymentGatewayError`, which keeps the payment `pending` so a later retry can still verify it.

## Money-safety invariants

> **⚠️ These invariants are load-bearing. Do not merge any change that weakens one of them.**
>
> 1. **Single activation point** — `payment_service.activate_subscription` is the only place a subscription is ever created/activated, and it is only called after a verified payment.
> 2. **Idempotent verification** — re-verifying the same payment never double-credits; `payments.transaction_id` carries a DB-level **UNIQUE** constraint as the enforced backstop.
> 3. **Row lock + status branching** — verification takes `SELECT ... FOR UPDATE` on the payment row and branches on its current status (`pending` / `success` / `failed`), so concurrent callbacks serialize and settle exactly once.
> 4. **Quota decremented only after successful upload** — the worker calls `subscription_service.consume_download()` strictly *after* the file has been delivered to the user; failures and denials never consume quota.
> 5. **No balance/quota mutation outside designated services** — nothing outside `payment_service` / `subscription_service` may mutate payment status, subscriptions, `downloads_used`, or download counters.

## Zarinpal flow

```
 user taps "Buy" in bot
        │
        ▼
 bot ── POST /api/internal/payments/create ──▶ api
        {telegram_id, plan_id, gateway:"zarinpal"}      creates pending Payment row,
        │                                               calls Zarinpal request.json
        ▼
 bot sends the user the StartPay URL
        │ {payment_id, payment_url, authority}
        ▼
 user opens https://<zarinpal>/pg/StartPay/<authority> and pays
        │
        ▼
 Zarinpal redirects the browser:
        GET https://DOMAIN/payments/zarinpal/callback?Authority=...&Status=OK|NOK
        │
        ▼
 api: payment_service.verify_and_activate(authority, status)
        ├─ Status != OK        → mark failed (no verify call)
        ├─ row lock (FOR UPDATE) + status branch          (invariants 2–3)
        ├─ Zarinpal verify.json → ok → status=success,
        │    transaction_id=ref_id, activate_subscription  (invariant 1)
        └─ gateway unreachable → stays pending, retryable
        │
        ▼
 user sees an HTML result page (success / failure, fa+en)
```

Notes:

- Plans are priced in **Toman (IRT)** by default; the gateway converts to Rials (×10) because Zarinpal v4 amounts are IRR.
- Zarinpal verify code `100` = verified now, `101` = already verified — both count as success with the same `ref_id`.
- The callback base URL is `PAYMENT_CALLBACK_BASE_URL` (defaults to `https://$DOMAIN`).

## Sandbox toggle

```bash
# .env
ZARINPAL_MERCHANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ZARINPAL_SANDBOX=true    # true = sandbox.zarinpal.com (test), false = payment.zarinpal.com
```

Keep `ZARINPAL_SANDBOX=true` while testing — sandbox payments move no real money. Flip to `false` (and restart: `zed-downloader restart`) to go live.

## Adding a gateway — exact steps

1. **Write the gateway class** in `apps/api/app/payments/your_gateway.py`, subclassing `BasePaymentProvider` and implementing `create_payment` / `verify_payment`.
2. **Add one line to `GATEWAYS`** in `apps/api/app/services/payment_service.py`:
   ```python
   GATEWAYS: dict[str, type[BasePaymentProvider]] = {
       "zarinpal": ZarinpalGateway,
       "your_gateway": YourGateway,   # <-- add this
   }
   ```
3. **Add its callback route** in `apps/api/app/routes/payments.py` (mirror the Zarinpal callback: extract the gateway's authority/status params, call `verify_and_activate`, render the result page).
4. **Configure it from the panel** (plan/gateway settings) and expose whatever credentials it needs as env vars, following the `ZARINPAL_*` pattern.

Do **not** create subscriptions, mark payments successful, or touch quotas anywhere else — route everything through `verify_and_activate` / `activate_subscription` so the invariants above keep holding.

## v2 roadmap

Planned gateways: **Zibal**, **Telegram Stars**, **TON**, **TRON (USDT)** — each is one class + one registry line + one callback route, per the steps above.

See also: [API.md](API.md) for payment endpoints · [ADMIN.md](ADMIN.md) for plans/payments pages.
