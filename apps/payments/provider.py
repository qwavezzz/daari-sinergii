"""Alfa-Bank REST boundary. No card data enters this application.

https://alfabank.ru/sme/payservice/internet-acquiring/docs/connection-options/api/rest/
Status API version 03+ is required for captured/refunded amount verification.
"""

import json
import re
import uuid
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings


class PaymentError(Exception):
    pass


class InvalidPayment(PaymentError):
    pass


class PaymentUnavailable(PaymentError):
    pass


class PaymentNotFound(PaymentUnavailable):
    """The authenticated status API explicitly returned errorCode 6."""


def payment_origin(test):
    return "https://alfa.rbsuat.com" if test else "https://pay.alfabank.ru"


def safe_provider_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", value):
        raise InvalidPayment("Неверный идентификатор платёжного сервиса.")
    return value


def minor_units(amount):
    """Reject rounding, floats, and non-finite money at the protocol boundary."""
    try:
        if isinstance(amount, (float, bool)):
            raise ValueError
        value = Decimal(amount)
        minor = value * 100
        if not value.is_finite() or minor < 0 or minor != minor.to_integral_value():
            raise ValueError
        return int(minor)
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise InvalidPayment("Некорректная сумма платежа.") from exc


def protocol_integer(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,20}", str(value)):
        raise InvalidPayment("Некорректное числовое поле платёжного сервиса.")
    return int(value)


def safe_confirmation_url(value, test, provider_id):
    try:
        url = urlparse(value)
        host = urlparse(payment_origin(test)).hostname
        if (
            not isinstance(value, str)
            or any(ord(char) < 32 for char in value)
            or "\\" in value
            or url.scheme != "https"
            or url.hostname != host
            or url.port not in (None, 443)
            or url.username is not None
            or url.password is not None
            or url.fragment
            or not re.fullmatch(r"/payment/merchants/[A-Za-z0-9_-]+/payment_[a-z]{2}\.html", url.path)
            or parse_qs(url.query).get("mdOrder") != [provider_id]
        ):
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise InvalidPayment("Неожиданный адрес платёжной страницы.") from exc
    return value


def named_parameters(values):
    result = {}
    for value in values:
        name = value["name"]
        if name in result:
            raise InvalidPayment("Неоднозначные параметры платежа.")
        result[name] = value["value"]
    return result


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
    order_number: str = ""
    refunded_amount: Decimal = Decimal("0.00")

    @classmethod
    def parse(cls, data, *, account_id, test, provider_id=None):
        try:
            status_code = protocol_integer(data["orderStatus"])
            statuses = {
                0: "pending",
                1: "waiting_for_capture",
                2: "succeeded",
                3: "canceled",
                4: "succeeded",
                5: "pending",
                6: "canceled",
            }
            status = statuses[status_code]
            amount = protocol_integer(data["amount"])
            if not 0 < amount <= 999999999999 or str(data["currency"]) != "643":
                raise ValueError
            params = named_parameters(data["merchantOrderParams"])
            order_id = str(uuid.UUID(params["order_id"]))
            order_number = str(uuid.UUID(data["orderNumber"]))
            attributes = named_parameters(data.get("attributes", []))
            response_id = data.get("orderId") or attributes.get("mdOrder") or provider_id
            response_id = safe_provider_id(response_id)
            if (provider_id and response_id != provider_id) or (
                attributes.get("mdOrder") and attributes["mdOrder"] != response_id
            ):
                raise ValueError
            amount_info = data.get("paymentAmountInfo", {})
            refunded = protocol_integer(amount_info.get("refundedAmount", 0))
            deposited = protocol_integer(amount_info.get("depositedAmount", 0))
            if status == "succeeded":
                if protocol_integer(data["actionCode"]) != 0:
                    raise ValueError
                if not {"depositedAmount", "refundedAmount"} <= amount_info.keys() or refunded > amount:
                    raise ValueError
                if status_code == 4 and not refunded:
                    raise ValueError
                # The status API documents depositedAmount as captured money;
                # refund.do's expectedDepositedAmount documents a changing balance.
                # Accept either authenticated interpretation only when it exactly
                # accounts for the original total: gross capture, or net + refunds.
                if deposited != amount and deposited + refunded != amount:
                    raise ValueError
            elif deposited or refunded:
                raise ValueError
            return cls(
                response_id,
                status,
                Decimal(amount) / 100,
                "RUB",
                order_id,
                account_id,
                test,
                status == "succeeded",
                order_number=order_number,
                refunded_amount=Decimal(refunded) / 100,
            )
        except (KeyError, TypeError, ValueError, AttributeError, InvalidOperation) as exc:
            raise InvalidPayment("Альфа-Банк вернул неполные или противоречивые данные.") from exc


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward form credentials to another URL (including 307/308).
        return None


class AlfaBankClient:
    def __init__(self):
        self.account_id = settings.ALFABANK_USERNAME
        self.test = settings.ALFABANK_TEST_MODE
        if not settings.ALFABANK_ENABLED or not self.account_id or not settings.ALFABANK_PASSWORD:
            raise PaymentUnavailable("Онлайн-оплата пока не подключена.")
        if not self.test and (
            not settings.ALFABANK_LIVE_APPROVED or settings.ALFABANK_RECEIPT_MODE not in {"bank", "external"}
        ):
            raise PaymentUnavailable(
                "Рабочая оплата требует согласованной схемы чеков и подтверждения запуска."
            )
        self.base_url = payment_origin(self.test) + "/payment/rest/"
        self.opener = build_opener(NoRedirect())

    def request(self, method, payload):
        if method not in {"register.do", "getOrderStatusExtended.do"}:
            raise InvalidPayment("Недоступный метод платёжного сервиса.")
        data = {**payload, "userName": self.account_id, "password": settings.ALFABANK_PASSWORD}
        request = Request(
            self.base_url + method,
            data=urlencode(data).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=12) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise ValueError
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ValueError
                return result
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raise PaymentUnavailable(
                "Не удалось получить подтверждение Альфа-Банка. Проверка продолжится."
            ) from exc

    def get_payment(self, provider_id=None, *, order_number=None):
        if provider_id:
            payload = {"orderId": safe_provider_id(provider_id)}
        elif order_number:
            payload = {"orderNumber": str(uuid.UUID(str(order_number)))}
        else:
            raise InvalidPayment("Не указан номер платежа.")
        data = self.request("getOrderStatusExtended.do", payload)
        error = protocol_integer(data.get("errorCode", 0))
        if error == 6:
            raise PaymentNotFound("Платёж ещё не найден в Альфа-Банке.")
        if error:
            raise PaymentUnavailable("Альфа-Банк пока не подтвердил состояние платежа.")
        result = VerifiedPayment.parse(
            data, account_id=self.account_id, test=self.test, provider_id=provider_id
        )
        if order_number and result.order_number != str(order_number):
            raise InvalidPayment("Номер операции не совпадает с запросом.")
        return result

    def create_payment(self, payload, key):
        number = str(key)
        if payload.get("orderNumber") != number:
            raise InvalidPayment("Номер операции не совпадает с сохранённым запросом.")
        try:
            data = self.request("register.do", payload)
        except PaymentUnavailable:
            return self.get_payment(order_number=number)
        error = protocol_integer(data.get("errorCode", 0))
        if error == 1:
            return self.get_payment(order_number=number)
        if error:
            raise PaymentUnavailable("Альфа-Банк не подтвердил регистрацию платежа. Требуется проверка.")
        provider_id = safe_provider_id(data.get("orderId"))
        confirmation = safe_confirmation_url(data.get("formUrl"), self.test, provider_id)
        verified = self.get_payment(provider_id)
        if verified.order_number != number:
            raise InvalidPayment("Номер операции не совпадает с регистрацией.")
        return replace(verified, confirmation_url=confirmation)
