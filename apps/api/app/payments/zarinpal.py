"""Zarinpal v4 REST gateway (sandbox toggle via ZARINPAL_SANDBOX)."""
from decimal import Decimal

import httpx

from app.config import get_settings
from app.payments.base import BasePaymentProvider, PaymentGatewayError, PaymentInit, PaymentVerdict


class ZarinpalGateway(BasePaymentProvider):
    gateway_name = "zarinpal"

    @property
    def _host(self) -> str:
        return "sandbox.zarinpal.com" if get_settings().ZARINPAL_SANDBOX else "payment.zarinpal.com"

    @property
    def _api_base(self) -> str:
        return f"https://{self._host}/pg/v4/payment"

    def _start_pay_url(self, authority: str) -> str:
        return f"https://{self._host}/pg/StartPay/{authority}"

    @staticmethod
    def _amount_in_rials(amount: Decimal, currency: str) -> int:
        # Zarinpal v4 amounts are in Rials (IRR). Our plans are priced in
        # Toman (IRT) by default: 1 Toman = 10 Rials.
        if currency.upper() in ("IRT", "TOMAN"):
            return int(amount) * 10
        return int(amount)

    async def _post(self, path: str, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{self._api_base}/{path}", json=payload)
        except httpx.HTTPError as exc:
            raise PaymentGatewayError(f"zarinpal unreachable: {exc}") from exc
        if resp.status_code >= 500:
            raise PaymentGatewayError(f"zarinpal 5xx: {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise PaymentGatewayError("zarinpal returned non-JSON response") from exc
        return body

    async def create_payment(
        self, *, amount: Decimal, currency: str, description: str, callback_url: str
    ) -> PaymentInit:
        settings = get_settings()
        if not settings.ZARINPAL_MERCHANT_ID:
            raise PaymentGatewayError("ZARINPAL_MERCHANT_ID is not configured")
        body = await self._post(
            "request.json",
            {
                "merchant_id": settings.ZARINPAL_MERCHANT_ID,
                "amount": self._amount_in_rials(amount, currency),
                "currency": "IRR",
                "callback_url": callback_url,
                "description": description,
            },
        )
        data = body.get("data") or {}
        if data.get("code") != 100 or not data.get("authority"):
            errors = body.get("errors") or {}
            raise PaymentGatewayError(f"zarinpal request rejected: {errors or data}")
        authority = data["authority"]
        return PaymentInit(authority=authority, payment_url=self._start_pay_url(authority))

    async def verify_payment(
        self, *, authority: str, amount: Decimal, currency: str
    ) -> PaymentVerdict:
        settings = get_settings()
        body = await self._post(
            "verify.json",
            {
                "merchant_id": settings.ZARINPAL_MERCHANT_ID,
                "amount": self._amount_in_rials(amount, currency),
                "authority": authority,
            },
        )
        data = body.get("data") or {}
        code = data.get("code")
        # 100 = verified now; 101 = this authority was already verified by
        # Zarinpal before (same transaction — still the same ref_id).
        if code in (100, 101) and data.get("ref_id") is not None:
            return PaymentVerdict(ok=True, ref_id=str(data["ref_id"]), message=f"code {code}")
        errors = body.get("errors") or {}
        return PaymentVerdict(ok=False, message=f"verify rejected: {errors or data}")
