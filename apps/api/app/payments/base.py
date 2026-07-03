"""Payment gateway seam.

To add a gateway:
1. Write a BasePaymentProvider subclass in app/payments/your_gateway.py.
2. Add one line to GATEWAYS in app/services/payment_service.py.
3. Add its callback route in app/routes/payments.py.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


class PaymentGatewayError(Exception):
    """Raised when the gateway cannot even start/answer a request.
    Verification failures are NOT exceptions — they return PaymentVerdict(ok=False)."""


@dataclass
class PaymentInit:
    authority: str  # gateway session/authority token
    payment_url: str  # where the user must be redirected to pay


@dataclass
class PaymentVerdict:
    ok: bool
    ref_id: str | None = None  # gateway transaction reference (unique)
    message: str = ""


class BasePaymentProvider(ABC):
    gateway_name: str = "base"

    @abstractmethod
    async def create_payment(
        self, *, amount: Decimal, currency: str, description: str, callback_url: str
    ) -> PaymentInit: ...

    @abstractmethod
    async def verify_payment(
        self, *, authority: str, amount: Decimal, currency: str
    ) -> PaymentVerdict: ...
