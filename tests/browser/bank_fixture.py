"""Synthetic bank protocol for browser redirect/CSP regression, never imported by apps."""

import json
import os
from pathlib import Path

from django.conf import settings
from apps.payments.models import PaymentAttempt
from apps.payments.provider import AlfaBankClient


def install_bank_fixture():
    registered = {}

    def request(self, method, payload):
        if method == "register.do":
            number = payload["orderNumber"]
            registered[number] = dict(payload)
            # Browser assertions can follow the same return URL as the bank.
            path = (
                Path(settings.BASE_DIR)
                / "var"
                / f"browser-bank-{os.environ.get('BROWSER_TEST_PORT', '8001')}.json"
            )
            path.write_text(
                json.dumps({key: value["returnUrl"] for key, value in registered.items()}), encoding="utf-8"
            )
            return {
                "orderId": number,
                "formUrl": f"https://alfa.rbsuat.com/payment/merchants/browser/payment_ru.html?mdOrder={number}",
            }
        number = payload.get("orderId") or payload.get("orderNumber")
        if number not in registered:
            return {"errorCode": "6"}
        attempt = PaymentAttempt.objects.select_related("order").get(idempotence_key=number)
        return {
            "errorCode": "0",
            "orderId": number,
            "orderNumber": number,
            "orderStatus": 0,
            "actionCode": 0,
            "amount": int(attempt.amount * 100),
            "currency": "643",
            "merchantOrderParams": [{"name": "order_id", "value": str(attempt.order.public_id)}],
        }

    AlfaBankClient.request = request
