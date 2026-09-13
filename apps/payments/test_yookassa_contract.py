import base64
import json
from dataclasses import replace
from io import BytesIO, StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.orders.models import Order
from apps.orders.services import create_order
from apps.orders.test_support import checkout_data, fixture_cart

from .models import PaymentAttempt, PaymentEvent
from .provider import InvalidPayment, PaymentUnavailable, VerifiedPayment, YooKassaClient
from .services import apply_payment, reconcile_attempt, start_payment


@override_settings(
    YOOKASSA_ENABLED=True,
    YOOKASSA_TEST_MODE=True,
    YOOKASSA_SHOP_ID="12345",
    YOOKASSA_SECRET_KEY="test-contract-fixture",
    YOOKASSA_RECEIPT_MODE="unconfigured",
)
class YooKassaContractTests(TestCase):
    test_webhook = "/payments/yookassa/test/webhook/"
    live_webhook = "/payments/yookassa/webhook/"

    def setUp(self):
        cart, self.product, method = fixture_cart()
        self.order = create_order(cart, checkout_data(cart, method), cart.session_key)

    def payment_data(self, status="pending"):
        data = {
            "id": "23d93cac-000f-5000-8000-126628f15141",
            "status": status,
            "paid": status in {"waiting_for_capture", "succeeded"},
            "amount": {"value": str(self.order.total), "currency": "RUB"},
            "metadata": {"order_id": str(self.order.public_id)},
            "recipient": {"account_id": "12345", "gateway_id": "67890"},
            "test": True,
        }
        if status == "pending":
            data["confirmation"] = {
                "type": "redirect",
                "confirmation_url": "https://yoomoney.ru/api-pages/v2/payment-confirm/epl?orderId="
                + data["id"],
            }
        if status == "canceled":
            data["cancellation_details"] = {"party": "payment_network", "reason": "insufficient_funds"}
        return data

    def create_attempt(self, provider_id=True):
        return PaymentAttempt.objects.create(
            order=self.order,
            amount=self.order.total,
            currency="RUB",
            provider_id=self.payment_data()["id"] if provider_id else None,
            state="pending" if provider_id else "unknown",
        )

    def post_notification(self, status="succeeded", url=None):
        return self.client.post(
            url or self.test_webhook,
            {"type": "notification", "event": "payment." + status, "object": self.payment_data(status)},
            content_type="application/json",
            HTTP_HOST="shop.localhost",
        )

    def test_creation_matches_api_contract_and_keeps_card_data_on_provider_page(self):
        calls = []

        def api(request, timeout):
            calls.append(request)
            self.assertEqual(timeout, 12)
            auth = base64.b64encode(b"12345:test-contract-fixture").decode()
            self.assertEqual(request.get_header("Authorization"), "Basic " + auth)
            if request.method == "GET":
                self.assertEqual(request.full_url, "https://api.yookassa.ru/v3/me")
                data = {"account_id": "12345", "test": True}
            else:
                self.assertEqual(request.full_url, "https://api.yookassa.ru/v3/payments")
                self.assertEqual(request.get_header("Content-type"), "application/json")
                payload = json.loads(request.data)
                self.assertEqual(payload["amount"], {"value": "150.00", "currency": "RUB"})
                self.assertIs(payload["capture"], True)
                self.assertEqual(payload["payment_method_data"], {"type": "bank_card"})
                self.assertEqual(payload["metadata"]["order_id"], str(self.order.public_id))
                self.assertEqual(payload["confirmation"]["type"], "redirect")
                self.assertTrue(payload["confirmation"]["return_url"].endswith(self.order.get_absolute_url()))
                # Test mode is selected by credentials, not by a create-request flag.
                self.assertNotIn("test", payload)
                self.assertLessEqual(len(payload["description"]), 128)
                data = self.payment_data()
            return BytesIO(json.dumps(data).encode())

        with patch("apps.payments.provider.urlopen", side_effect=api):
            attempt = start_payment(self.order.pk)
        self.assertEqual([request.method for request in calls], ["GET", "POST"])
        self.assertEqual(calls[1].get_header("Idempotence-key"), str(attempt.idempotence_key))
        self.assertEqual(attempt.confirmation_url, self.payment_data()["confirmation"]["confirmation_url"])

    def test_test_webhook_verifies_api_and_deduplicates_success(self):
        self.create_attempt()
        with patch("apps.payments.provider.urlopen", return_value=None) as api:
            api.side_effect = lambda *args, **kwargs: BytesIO(
                json.dumps(self.payment_data("succeeded")).encode()
            )
            self.assertEqual(self.post_notification().status_code, 200)
            self.assertEqual(self.post_notification().status_code, 200)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.financial_status, "paid")
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(self.order.notifications.filter(event="paid").count(), 2)
        self.assertEqual(PaymentEvent.objects.count(), 1)

    def test_notification_can_arrive_before_creation_response(self):
        attempt = self.create_attempt(provider_id=False)
        result = VerifiedPayment.parse(self.payment_data("succeeded"))
        with patch.object(YooKassaClient, "get_payment", return_value=result):
            self.assertEqual(self.post_notification().status_code, 200)
        attempt.refresh_from_db()
        self.assertEqual(attempt.provider_id, result.id)
        self.assertEqual(attempt.state, "succeeded")

    def test_webhook_urls_reject_other_environment_before_calling_api(self):
        with patch("apps.payments.views.YooKassaClient") as provider:
            self.assertEqual(self.post_notification(url=self.live_webhook).status_code, 404)
            with override_settings(YOOKASSA_TEST_MODE=False):
                self.assertEqual(self.post_notification().status_code, 404)
            provider.assert_not_called()

    def test_live_webhook_still_accepts_verified_live_payment(self):
        self.create_attempt()
        Order.objects.filter(pk=self.order.pk).update(test_mode=False)
        result = replace(VerifiedPayment.parse(self.payment_data("succeeded")), test=False)
        with (
            override_settings(YOOKASSA_TEST_MODE=False),
            patch("apps.payments.views.YooKassaClient") as provider,
        ):
            provider.return_value.get_payment.return_value = result
            self.assertEqual(self.post_notification(url=self.live_webhook).status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "paid")

    def test_test_payment_cannot_pay_a_live_order(self):
        attempt = self.create_attempt()
        Order.objects.filter(pk=self.order.pk).update(test_mode=False)
        with self.assertRaises(InvalidPayment):
            apply_payment(attempt.pk, VerifiedPayment.parse(self.payment_data("succeeded")))
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "unpaid")
        self.assertFalse(self.order.notifications.filter(event="paid").exists())

    def test_test_webhook_rejects_live_api_response_even_if_body_claims_test(self):
        self.create_attempt()
        result = replace(VerifiedPayment.parse(self.payment_data("succeeded")), test=False)
        with patch.object(YooKassaClient, "get_payment", return_value=result):
            self.assertEqual(self.post_notification().status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "unpaid")
        self.assertFalse(self.order.notifications.filter(event="paid").exists())

    def test_success_requires_paid_flag_from_api(self):
        attempt = self.create_attempt()
        result = replace(VerifiedPayment.parse(self.payment_data("succeeded")), paid=False)
        with self.assertRaises(InvalidPayment):
            apply_payment(attempt.pk, result)
        self.assertFalse(self.order.notifications.filter(event="paid").exists())

    def test_refund_notification_uses_api_amount_and_is_idempotent(self):
        attempt = self.create_attempt()
        apply_payment(attempt.pk, VerifiedPayment.parse(self.payment_data("succeeded")))
        refund = {
            "id": "contract-refund",
            "payment_id": attempt.provider_id,
            "status": "succeeded",
            "amount": {"value": "50.00", "currency": "RUB"},
        }
        notification = {
            "type": "notification",
            "event": "refund.succeeded",
            "object": {**refund, "amount": {"value": "150.00", "currency": "RUB"}},
        }
        calls = []

        def api(request, timeout):
            calls.append((request.method, request.full_url))
            data = refund if "/refunds/" in request.full_url else self.payment_data("succeeded")
            return BytesIO(json.dumps(data).encode())

        with patch("apps.payments.provider.urlopen", side_effect=api):
            for _ in range(2):
                response = self.client.post(
                    self.test_webhook,
                    notification,
                    content_type="application/json",
                    HTTP_HOST="shop.localhost",
                )
                self.assertEqual(response.status_code, 200)
        self.assertEqual(
            calls,
            [
                ("GET", "https://api.yookassa.ru/v3/refunds/contract-refund"),
                ("GET", "https://api.yookassa.ru/v3/payments/" + attempt.provider_id),
            ]
            * 2,
        )
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.financial_status, "part_refunded")
        self.assertEqual(attempt.refunds.count(), 1)
        self.assertEqual(attempt.refunds.get().amount, 50)
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(self.order.notifications.filter(event="refund-contract-refund").count(), 2)

    def test_reconciliation_rejects_orders_from_other_mode_without_provider_request(self):
        for has_provider_id in (True, False):
            with self.subTest(has_provider_id=has_provider_id):
                PaymentAttempt.objects.all().delete()
                attempt = self.create_attempt(provider_id=has_provider_id)
                Order.objects.filter(pk=self.order.pk).update(test_mode=False)
                with patch("apps.payments.services.YooKassaClient") as provider:
                    with self.assertRaises(PaymentUnavailable):
                        reconcile_attempt(attempt.pk)
                    provider.assert_not_called()

    def test_background_reconciliation_skips_orders_from_other_mode(self):
        attempt = self.create_attempt()
        Order.objects.filter(pk=self.order.pk).update(test_mode=False)
        with patch("apps.payments.management.commands.reconcile_payments.reconcile_attempt") as reconcile:
            call_command("reconcile_payments", stdout=StringIO())
        reconcile.assert_not_called()
        attempt.refresh_from_db()
        self.assertIsNone(attempt.last_checked_at)

    def test_waiting_for_capture_is_not_completed_payment(self):
        attempt = self.create_attempt()
        apply_payment(attempt.pk, VerifiedPayment.parse(self.payment_data("waiting_for_capture")))
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertNotEqual(self.order.financial_status, "paid")
        self.assertEqual((self.product.stock, self.product.reserved_stock), (5, 1))
        self.assertFalse(self.order.notifications.filter(event="paid").exists())

    def test_declined_card_releases_reserve_without_success_emails(self):
        self.create_attempt()
        with patch.object(
            YooKassaClient, "get_payment", return_value=VerifiedPayment.parse(self.payment_data("canceled"))
        ):
            self.assertEqual(self.post_notification("canceled").status_code, 200)
        self.product.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.reserved_stock), (5, 0))
        self.assertEqual((self.order.status, self.order.financial_status), ("canceled", "unpaid"))
        self.assertFalse(self.order.notifications.filter(event="paid").exists())

    def test_malformed_notifications_return_400_without_calling_provider(self):
        for body in (None, [], "invalid", 1, {"object": None}, {"object": []}):
            with self.subTest(body=body), patch("apps.payments.views.YooKassaClient") as provider:
                response = self.client.post(
                    self.test_webhook,
                    json.dumps(body),
                    content_type="application/json",
                    HTTP_HOST="shop.localhost",
                )
                self.assertEqual(response.status_code, 400)
                provider.assert_not_called()
