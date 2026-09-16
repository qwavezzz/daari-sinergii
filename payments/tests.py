from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from orders.models import Notification, Order, StockReservation
from orders.notifications import build_notification_email
from orders.services import create_order
from orders.test_support import checkout_data, fixture_cart
from .models import PaymentAttempt, Refund
from .provider import InvalidPayment, PaymentUnavailable, VerifiedPayment
from .services import apply_payment, apply_refund, reconcile_attempt, start_payment


class FakeClient:
    def __init__(self, payment):
        self.payment = payment
        self.calls = []
        self.fail = False

    def create_payment(self, payload, key):
        self.calls.append((payload, key))
        if self.fail:
            raise PaymentUnavailable("Тестовый таймаут")
        return self.payment

    def get_payment(self, provider_id):
        return self.payment

    def list_refunds(self, provider_id):
        return []


@override_settings(YOOKASSA_SHOP_ID="test-shop", YOOKASSA_TEST_MODE=True)
class PaymentTests(TestCase):
    def setUp(self):
        cart, self.product, method = fixture_cart()
        self.order = create_order(cart, checkout_data(cart, method), cart.session_key)
        self.result = VerifiedPayment(
            "test-payment-id",
            "pending",
            self.order.total,
            "RUB",
            str(self.order.public_id),
            "test-shop",
            True,
            False,
            "https://yookassa.ru/checkout/test",
        )
        self.provider = FakeClient(self.result)

    def attempt(self):
        return start_payment(self.order.pk, self.provider)

    def succeeded(self, attempt=None):
        attempt = attempt or self.attempt()
        return apply_payment(attempt.pk, replace(self.result, status="succeeded", paid=True))

    def test_timeout_retries_same_payload_and_key(self):
        self.provider.fail = True
        with self.assertRaises(PaymentUnavailable):
            self.attempt()
        self.assertEqual(PaymentAttempt.objects.get().state, "unknown")
        self.provider.fail = False
        self.attempt()
        self.assertEqual(self.provider.calls[0], self.provider.calls[1])
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_expired_idempotency_window_does_not_create_another_payment(self):
        self.provider.fail = True
        with self.assertRaises(PaymentUnavailable):
            self.attempt()
        PaymentAttempt.objects.update(created_at=timezone.now() - timedelta(hours=25))
        self.provider.fail = False
        with self.assertRaises(PaymentUnavailable):
            self.attempt()
        self.assertEqual(len(self.provider.calls), 1)

    def test_success_deduplicates_stock_notifications_and_never_regresses(self):
        attempt = self.succeeded()
        self.succeeded(attempt)
        apply_payment(attempt.pk, self.result)
        self.product.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.reserved_stock), (4, 0))
        self.assertEqual(self.order.financial_status, "paid")
        self.assertEqual(self.order.notifications.filter(event="paid").count(), 2)

    def test_wrong_amount_currency_shop_order_and_test_flag_rejected(self):
        attempt = self.attempt()
        for changes in (
            {"amount": Decimal("1")},
            {"currency": "USD"},
            {"account_id": "evil"},
            {"order_id": "other"},
            {"test": False},
        ):
            with self.subTest(changes=changes), self.assertRaises(InvalidPayment):
                apply_payment(attempt.pk, replace(self.result, status="succeeded", paid=True, **changes))
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "pending")

    def test_cancellation_releases_only_once(self):
        attempt = self.attempt()
        result = replace(self.result, status="canceled")
        apply_payment(attempt.pk, result)
        apply_payment(attempt.pk, result)
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.reserved_stock), (5, 0))

    def test_late_payment_without_stock_is_visible_for_resolution(self):
        attempt = self.attempt()
        apply_payment(attempt.pk, replace(self.result, status="canceled"))
        self.product.stock = 0
        self.product.save(update_fields=["stock"])
        self.succeeded(attempt)
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "paid")
        self.assertTrue(self.order.needs_attention)
        self.assertEqual(self.order.reservations.get().state, "conflict")

    def test_duplicate_successful_payment_flags_anomaly(self):
        self.succeeded()
        second = PaymentAttempt.objects.create(
            order=self.order,
            amount=self.order.total,
            currency="RUB",
            state="canceled",
            provider_id="second-payment-id",
        )
        apply_payment(second.pk, replace(self.result, id="second-payment-id", status="succeeded", paid=True))
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertTrue(self.order.needs_attention)
        self.assertEqual(self.product.stock, 4)

    def test_refund_is_idempotent_and_does_not_restock(self):
        attempt = self.succeeded()
        refund = {
            "id": "refund-id",
            "payment_id": attempt.provider_id,
            "status": "succeeded",
            "amount": {"value": "150.00", "currency": "RUB"},
        }
        apply_refund(attempt.pk, refund)
        apply_refund(attempt.pk, refund)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.financial_status, "refunded")
        self.assertEqual(Refund.objects.count(), 1)
        self.assertEqual(self.product.stock, 4)

    def test_lost_webhook_reconciles_authoritative_status(self):
        attempt = self.attempt()
        self.provider.payment = replace(self.result, status="succeeded", paid=True)
        reconcile_attempt(attempt.pk, self.provider)
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "paid")

    def test_refund_mail_uses_confirmed_event_amount_and_handles_uuid_ids(self):
        attempt = self.succeeded()
        refund_id = "12345678-1234-1234-1234-123456789abc"
        refund = {
            "id": refund_id,
            "payment_id": attempt.provider_id,
            "status": "pending",
            "amount": {"value": "40.00", "currency": "RUB"},
        }
        apply_refund(attempt.pk, refund)
        self.assertFalse(Notification.objects.filter(event__startswith="refund").exists())
        refund["status"] = "succeeded"
        apply_refund(attempt.pk, refund)
        apply_refund(attempt.pk, refund)
        notices = Notification.objects.filter(event=f"refund-{refund_id}")
        self.assertEqual(notices.count(), 2)
        notice = notices.first()
        notice.full_clean()
        self.assertEqual(Decimal(notice.payload["refund_amount"]), Decimal("40.00"))
        self.assertEqual(Decimal(notice.payload["refunded_total"]), Decimal("40.00"))
        next_refund = {
            **refund,
            "id": "second-refund",
            "status": "pending",
            "amount": {"value": "110.00", "currency": "RUB"},
        }
        apply_refund(attempt.pk, next_refund)
        self.assertFalse(Notification.objects.filter(event="refund-second-refund").exists())
        next_refund["status"] = "succeeded"
        apply_refund(attempt.pk, next_refund)
        full_notice = Notification.objects.filter(event="refunded").first()
        self.assertEqual(full_notice.payload["refund_amount"], "110.00")
        notice.refresh_from_db()
        self.assertEqual(notice.payload["refund_amount"], "40.00")
        self.assertIn("Возврат по этому уведомлению: 40 ₽", build_notification_email(notice).body)

    def test_webhook_payload_is_not_trusted(self):
        attempt = self.attempt()
        payload = {
            "type": "notification",
            "event": "payment.succeeded",
            "object": {"id": attempt.provider_id, "status": "succeeded"},
        }
        with patch("payments.views.YooKassaClient", return_value=self.provider):
            response = self.client.post(
                "/payments/yookassa/webhook/",
                payload,
                content_type="application/json",
                HTTP_HOST="shop.localhost",
            )
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "pending")

    def test_webhook_temporary_failure_is_not_acknowledged(self):
        attempt = self.attempt()
        with patch("payments.views.YooKassaClient", side_effect=PaymentUnavailable("offline")):
            response = self.client.post(
                "/payments/yookassa/webhook/",
                {"type": "notification", "event": "payment.succeeded", "object": {"id": attempt.provider_id}},
                content_type="application/json",
                HTTP_HOST="shop.localhost",
            )
        self.assertEqual(response.status_code, 503)

    def test_expiry_does_not_release_unknown_payment_reservation(self):
        self.provider.fail = True
        with self.assertRaises(PaymentUnavailable):
            self.attempt()
        StockReservation.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        with patch(
            "payments.management.commands.reconcile_payments.reconcile_attempt",
            side_effect=PaymentUnavailable("offline"),
        ):
            call_command("reconcile_payments", verbosity=0)
        self.assertEqual(self.order.reservations.get().state, "active")

    def test_notification_failure_keeps_order_and_queue(self):
        with patch("orders.notifications.EmailMultiAlternatives.send", side_effect=OSError("test")):
            call_command("send_notifications", verbosity=0)
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())
        self.assertEqual(Notification.objects.filter(sent_at__isnull=True).count(), 2)

    def test_old_unknown_attempt_is_not_starved_by_recent_succeeded_refund_polling(self):
        old = self.attempt()
        PaymentAttempt.objects.filter(pk=old.pk).update(
            state="unknown",
            provider_id=None,
            created_at=timezone.now() - timedelta(days=45),
            last_checked_at=None,
        )
        with patch(
            "payments.management.commands.reconcile_payments.reconcile_attempt",
            side_effect=PaymentUnavailable("offline"),
        ) as reconcile:
            call_command("reconcile_payments", limit=1, verbosity=0)
        reconcile.assert_called_once_with(old.pk)
