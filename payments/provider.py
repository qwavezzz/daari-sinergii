"""Small explicit YooKassa API boundary. No card data enters this application."""

import base64
import json
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from django.conf import settings


class PaymentError(Exception):
    pass


class InvalidPayment(PaymentError):
    pass


class PaymentUnavailable(PaymentError):
    pass


def safe_provider_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", value):
        raise InvalidPayment("Неверный идентификатор платёжного сервиса.")
    return value


@dataclass(frozen=True)
class VerifiedPayment:
    id: str
    status: str
    amount: Decimal
    currency: str
    order_id: str
    account_id: str
    test: bool
    paid: bool
    confirmation_url: str = ""

    @classmethod
    def parse(cls, data):
        try:
            confirmation = data.get("confirmation", {}).get("confirmation_url", "")
            if confirmation:
                url = urlparse(confirmation)
                if (
                    url.scheme != "https"
                    or not url.hostname
                    or not (
                        url.hostname == "yookassa.ru"
                        or url.hostname.endswith(".yookassa.ru")
                        or url.hostname == "yoomoney.ru"
                        or url.hostname.endswith(".yoomoney.ru")
                    )
                ):
                    raise InvalidPayment("Неожиданный адрес платёжной страницы.")
            amount = Decimal(data["amount"]["value"])
            if not amount.is_finite() or amount <= 0:
                raise ValueError("amount")
            order_id = str(uuid.UUID(str(data["metadata"]["order_id"])))
            return cls(
                safe_provider_id(data["id"]),
                data["status"],
                amount,
                data["amount"]["currency"],
                order_id,
                str(data["recipient"]["account_id"]),
                data["test"],
                data.get("paid") is True,
                confirmation,
            )
        except (KeyError, TypeError, ValueError, AttributeError, InvalidOperation) as exc:
            raise InvalidPayment("Платёжный сервис вернул неполные данные.") from exc


class YooKassaClient:
    base_url = "https://api.yookassa.ru/v3/"

    def __init__(self):
        if not settings.YOOKASSA_ENABLED or not settings.YOOKASSA_SHOP_ID or not settings.YOOKASSA_SECRET_KEY:
            raise PaymentUnavailable("Онлайн-оплата пока не подключена.")
        if not settings.YOOKASSA_TEST_MODE and (
            not settings.YOOKASSA_LIVE_APPROVED
            or settings.YOOKASSA_RECEIPT_MODE not in {"provider", "external"}
        ):
            raise PaymentUnavailable(
                "Рабочая оплата требует согласованной схемы чеков и подтверждения запуска."
            )

    def request(self, method, path, payload=None, idempotence_key=None):
        auth = base64.b64encode(
            f"{settings.YOOKASSA_SHOP_ID}:{settings.YOOKASSA_SECRET_KEY}".encode()
        ).decode()
        headers = {"Authorization": "Basic " + auth, "Content-Type": "application/json"}
        if idempotence_key:
            headers["Idempotence-Key"] = str(idempotence_key)
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=12) as response:
                return json.loads(response.read(1024 * 1024))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            # Never include provider response bodies, auth headers, or contacts in logs/errors.
            raise PaymentUnavailable(
                "Не удалось получить подтверждение ЮKassa. Проверка продолжится автоматически."
            ) from exc

    def create_payment(self, payload, key):
        return VerifiedPayment.parse(self.request("POST", "payments", payload, key))

    def get_payment(self, provider_id):
        return VerifiedPayment.parse(self.request("GET", "payments/" + safe_provider_id(provider_id)))

    def get_refund(self, provider_id):
        return self.request("GET", "refunds/" + safe_provider_id(provider_id))

    def list_refunds(self, payment_id):
        cursor = None
        while True:
            query = {"payment_id": safe_provider_id(payment_id), "limit": 100}
            if cursor:
                query["cursor"] = cursor
            data = self.request("GET", "refunds?" + urlencode(query))
            yield from data.get("items", [])
            next_cursor = data.get("next_cursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
