import copy
import json
import uuid
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

from django.core.management import call_command
from django.db.models import Sum
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.orders.models import Notification, Order, StockReservation
from apps.orders.notifications import build_notification_email
from apps.orders.services import create_order
from apps.orders.test_support import checkout_data, fixture_cart
from .models import PaymentAttempt, Refund
from .provider import (
    AlfaBankClient,
    InvalidPayment,
    NoRedirect,
    PaymentNotFound,
    PaymentUnavailable,
    VerifiedPayment,
    minor_units,
    safe_confirmation_url,
)
from .services import apply_payment, apply_refund, payment_payload, reconcile_attempt, start_payment


def bank_url(provider_id="test-payment-id", *, test=True):
    host = "alfa.rbsuat.com" if test else "pay.alfabank.ru"
    return f"https://{host}/payment/merchants/test/payment_ru.html?mdOrder={provider_id}"


class FakeClient:
    def __init__(self, payment):
        self.payment = payment
        self.calls = []
        self.lookups = []
        self.registered = False
        self.fail = False

    def create_payment(self, payload, key):
        self.calls.append((copy.deepcopy(payload), key))
        if self.fail:
            raise PaymentUnavailable("Тестовый таймаут")
        self.registered = True
        self.payment = replace(self.payment, order_number=str(key))
        return self.payment

    def get_payment(self, provider_id=None, *, order_number=None):
        self.lookups.append((provider_id, order_number))
        if not self.registered:
            raise PaymentNotFound("Тестовый заказ ещё не зарегистрирован")
        return self.payment


@override_settings(
    ALFABANK_USERNAME="test-merchant",
    ALFABANK_TEST_MODE=True,
    ALFABANK_RECEIPT_MODE="unconfigured",
)
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
            "test-merchant",
            True,
            False,
            bank_url(),
        )
        self.provider = FakeClient(self.result)

    def attempt(self):
        attempt = start_payment(self.order.pk, self.provider)
        self.result = self.provider.payment
        return attempt

    def succeeded(self, attempt=None):
        attempt = attempt or self.attempt()
        return apply_payment(attempt.pk, replace(self.result, status="succeeded", paid=True))

    def test_saved_total_includes_delivery_and_key_before_request(self):
        attempt = self.attempt()
        self.assertEqual(attempt.request_payload["amount"], 15000)
        self.assertEqual(attempt.request_payload["orderNumber"], str(attempt.idempotence_key))
        self.assertEqual(attempt.request_payload["currency"], 643)
        self.assertNotIn("password", attempt.request_payload)

    def test_timeout_retries_same_number_only_after_authoritative_not_found(self):
        self.provider.fail = True
        with self.assertRaises(PaymentUnavailable):
            self.attempt()
        attempt = PaymentAttempt.objects.get()
        self.assertEqual(attempt.state, "unknown")
        self.provider.fail = False
        self.attempt()
        self.assertEqual(self.provider.calls[0], self.provider.calls[1])
        self.assertEqual(self.provider.lookups, [(None, str(attempt.idempotence_key))] * 2)
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_repeated_click_does_not_register_again(self):
        self.attempt()
        self.attempt()
        self.assertEqual(len(self.provider.calls), 1)

    def test_lost_registration_response_recovers_success_by_number(self):
        self.provider.fail = True
        with self.assertRaises(PaymentUnavailable):
            self.attempt()
        attempt = PaymentAttempt.objects.get()
        self.provider.registered = True
        self.provider.payment = replace(
            self.result,
            status="succeeded",
            paid=True,
            order_number=str(attempt.idempotence_key),
        )
        reconcile_attempt(attempt.pk, self.provider)
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "paid")
        self.assertEqual(len(self.provider.calls), 1)

    def test_expired_reservation_is_looked_up_but_never_registered(self):
        self.provider.fail = True
        with self.assertRaises(PaymentUnavailable):
            self.attempt()
        PaymentAttempt.objects.update(created_at=timezone.now() - timedelta(hours=25))
        StockReservation.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.provider.fail = False
        with self.assertRaises(PaymentUnavailable):
            self.attempt()
        self.assertEqual(len(self.provider.calls), 1)

    def test_recovered_pending_without_page_is_visible_for_manual_resolution(self):
        attempt = self.attempt()
        PaymentAttempt.objects.filter(pk=attempt.pk).update(provider_id=None, confirmation_url="")
        self.provider.payment = replace(self.result, confirmation_url="")
        recovered = reconcile_attempt(attempt.pk, self.provider)
        self.order.refresh_from_db()
        self.assertTrue(self.order.needs_attention)
        self.assertIn("адрес оплаты", recovered.last_error)
        self.assertEqual(len(self.provider.calls), 1)
        # A late successful status resolves this warning and never charges again.
        apply_payment(attempt.pk, replace(self.result, status="succeeded", paid=True))
        self.order.refresh_from_db()
        self.assertFalse(self.order.needs_attention)
        self.assertEqual(self.order.financial_status, "paid")

    def test_background_does_not_register_a_missing_order(self):
        self.provider.fail = True
        with self.assertRaises(PaymentUnavailable):
            self.attempt()
        with self.assertRaises(PaymentUnavailable):
            reconcile_attempt(PaymentAttempt.objects.get().pk, self.provider)
        self.assertEqual(len(self.provider.calls), 1)

    def test_lookup_network_error_never_triggers_registration(self):
        self.provider.get_payment = Mock(side_effect=PaymentUnavailable("offline"))
        with self.assertRaises(PaymentUnavailable):
            self.attempt()
        self.assertEqual(self.provider.calls, [])

    def test_success_deduplicates_stock_notifications_and_never_regresses(self):
        attempt = self.succeeded()
        self.succeeded(attempt)
        apply_payment(attempt.pk, self.result)
        self.product.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.reserved_stock), (4, 0))
        self.assertEqual(self.order.financial_status, "paid")
        self.assertEqual(self.order.notifications.filter(event="paid").count(), 2)

    def test_amount_currency_account_order_number_mode_status_and_redirect_mismatches_rejected(self):
        attempt = self.attempt()
        for changes in (
            {"amount": Decimal("1")},
            {"currency": "USD"},
            {"account_id": "evil"},
            {"order_id": "other"},
            {"order_number": str(uuid.uuid4())},
            {"test": False},
            {"status": "unknown"},
            {"paid": False},
            {"id": "other-payment"},
            {"confirmation_url": "https://attacker.example/pay"},
            {"refunded_amount": Decimal("151")},
        ):
            with self.subTest(changes=changes), self.assertRaises(InvalidPayment):
                result = replace(self.result, status="succeeded", paid=True)
                apply_payment(attempt.pk, replace(result, **changes))
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "pending")

    def test_cancellation_releases_only_once(self):
        attempt = self.attempt()
        canceled = replace(self.result, status="canceled")
        apply_payment(attempt.pk, canceled)
        apply_payment(attempt.pk, canceled)
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
            account_id="test-merchant",
        )
        apply_payment(
            second.pk,
            replace(
                self.result,
                id="second-payment-id",
                order_number=str(second.idempotence_key),
                confirmation_url=bank_url("second-payment-id"),
                status="succeeded",
                paid=True,
            ),
        )
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertTrue(self.order.needs_attention)
        self.assertEqual(self.product.stock, 4)

    def test_cumulative_partial_full_refunds_and_stale_snapshots(self):
        attempt = self.succeeded()
        paid = replace(self.result, status="succeeded", paid=True)
        partial = replace(paid, refunded_amount=Decimal("40.00"))
        apply_payment(attempt.pk, partial)
        apply_payment(attempt.pk, partial)
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "part_refunded")
        notice = Notification.objects.filter(event__startswith="refund-").first()
        self.assertEqual(notice.payload["refund_amount"], "40.00")
        self.assertIn("Возврат по этому уведомлению: 40 ₽", build_notification_email(notice).body)
        full = replace(paid, refunded_amount=Decimal("150.00"))
        apply_payment(attempt.pk, full)
        apply_payment(attempt.pk, partial)
        apply_payment(attempt.pk, paid)
        apply_payment(attempt.pk, full)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.financial_status, "refunded")
        self.assertEqual(Refund.objects.count(), 2)
        self.assertEqual(Refund.objects.aggregate(total=Sum("amount"))["total"], Decimal("150"))
        self.assertEqual(Notification.objects.filter(event="refunded").count(), 2)
        full_notice = Notification.objects.filter(event="refunded").first()
        self.assertEqual(Decimal(full_notice.payload["refund_amount"]), Decimal("110"))
        self.assertEqual((self.product.stock, self.product.reserved_stock), (4, 0))

    def test_refund_on_unknown_payment_or_wrong_identity_rejected(self):
        attempt = self.attempt()
        with self.assertRaises(InvalidPayment):
            apply_refund(attempt.pk, replace(self.result, refunded_amount=Decimal("40")))
        self.assertFalse(Refund.objects.exists())

    def test_first_observed_status_can_be_fully_refunded(self):
        attempt = self.attempt()
        apply_payment(
            attempt.pk,
            replace(
                self.result,
                status="succeeded",
                paid=True,
                refunded_amount=self.order.total,
            ),
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "refunded")
        self.assertEqual(self.order.paid_attempt_id, attempt.pk)

    def test_webhook_payload_is_not_trusted(self):
        attempt = self.attempt()
        with patch("apps.payments.services.AlfaBankClient", return_value=self.provider):
            response = self.client.post(
                "/payments/alfabank/webhook/",
                {"mdOrder": attempt.provider_id, "operation": "deposited", "status": "1", "amount": 1},
                HTTP_HOST="shop.localhost",
            )
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "pending")

    def test_webhook_temporary_failure_is_not_acknowledged(self):
        attempt = self.attempt()
        with patch("apps.payments.services.AlfaBankClient", side_effect=PaymentUnavailable("offline")):
            response = self.client.get(
                "/payments/alfabank/webhook/",
                {"mdOrder": attempt.provider_id},
                HTTP_HOST="shop.localhost",
            )
        self.assertEqual(response.status_code, 503)

    def test_webhook_unknown_ids_do_not_trigger_bank_requests(self):
        with patch("apps.payments.services.AlfaBankClient") as client:
            response = self.client.post(
                "/payments/alfabank/webhook/",
                {"mdOrder": "unknown"},
                HTTP_HOST="shop.localhost",
            )
        self.assertEqual(response.status_code, 404)
        client.assert_not_called()

    def test_expiry_does_not_release_unknown_payment_reservation(self):
        self.provider.fail = True
        with self.assertRaises(PaymentUnavailable):
            self.attempt()
        StockReservation.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        with patch(
            "apps.payments.management.commands.reconcile_payments.reconcile_attempt",
            side_effect=PaymentUnavailable(),
        ):
            call_command("reconcile_payments", verbosity=0)
        self.assertEqual(self.order.reservations.get().state, "active")

    def test_legacy_attempt_never_reaches_new_api_or_starts_new_payment(self):
        attempt = PaymentAttempt.objects.create(
            order=self.order,
            amount=self.order.total,
            provider="legacy",
            state="unknown",
        )
        with self.assertRaises(PaymentUnavailable):
            reconcile_attempt(attempt.pk, self.provider)
        with self.assertRaises(PaymentUnavailable):
            self.attempt()
        with patch("apps.payments.management.commands.reconcile_payments.reconcile_attempt") as reconcile:
            call_command("reconcile_payments", verbosity=0)
        reconcile.assert_not_called()
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.provider.lookups, [])

    def test_changed_account_or_environment_blocks_poll_before_network(self):
        attempt = self.attempt()
        self.provider.lookups.clear()
        for settings_change in ({"ALFABANK_USERNAME": "different"}, {"ALFABANK_TEST_MODE": False}):
            with self.subTest(settings_change=settings_change), override_settings(**settings_change):
                with self.assertRaises(PaymentUnavailable):
                    reconcile_attempt(attempt.pk, self.provider)
        self.assertEqual(self.provider.lookups, [])

    def test_live_demo_payment_blocked_before_attempt(self):
        self.order.items.update(sku="DEMO-001")
        with override_settings(ALFABANK_TEST_MODE=False), self.assertRaises(PaymentUnavailable):
            self.attempt()
        self.assertFalse(PaymentAttempt.objects.exists())

    def test_canceled_attempt_is_reconciled_for_late_success(self):
        attempt = self.attempt()
        apply_payment(attempt.pk, replace(self.result, status="canceled"))
        with patch("apps.payments.management.commands.reconcile_payments.reconcile_attempt") as reconcile:
            call_command("reconcile_payments", verbosity=0)
        reconcile.assert_called_once_with(attempt.pk)

    def test_live_payment_requires_complete_seller_and_purchase_terms(self):
        with override_settings(ALFABANK_TEST_MODE=False), self.assertRaises(PaymentUnavailable):
            self.attempt()
        self.assertFalse(PaymentAttempt.objects.exists())
        self.assertEqual(self.provider.calls, [])

    @override_settings(ALFABANK_TEST_MODE=False)
    def test_live_payment_rejects_test_or_unverified_cdek_quote_before_attempt(self):
        for snapshot, current_test in (
            ({"test_mode": True}, False),
            ({}, False),
            ({"test_mode": None}, False),
            ({"test_mode": "false"}, False),
            ({"test_mode": False}, True),
        ):
            with self.subTest(snapshot=snapshot, current_test=current_test):
                self.order.delivery_type = "cdek_pvz"
                self.order.delivery_snapshot = snapshot
                self.order.save(update_fields=["delivery_type", "delivery_snapshot"])
                with (
                    override_settings(CDEK_TEST_MODE=current_test),
                    self.assertRaisesMessage(
                        PaymentUnavailable,
                        "расчёта доставки СДЭК",
                    ),
                ):
                    self.attempt()
                self.assertFalse(PaymentAttempt.objects.exists())
                self.assertEqual(self.provider.calls, [])
                self.assertEqual(self.provider.lookups, [])

    @override_settings(ALFABANK_RECEIPT_MODE="bank", ALFABANK_TAX_SYSTEM=1)
    def test_receipt_maps_existing_tax_codes_and_includes_delivery(self):
        self.order.items.update(vat_code=4)
        self.order.delivery_vat_code = 1
        payload = payment_payload(self.order)
        receipt = json.loads(payload["orderBundle"])
        goods, delivery = receipt["cartItems"]["items"]
        self.assertEqual(goods["tax"]["taxType"], 6)
        self.assertEqual(delivery["tax"]["taxType"], 0)
        self.assertEqual(goods["itemAmount"] + delivery["itemAmount"], payload["amount"])
        self.assertEqual(delivery["itemAttributes"]["attributes"][1]["value"], "4")
        self.assertEqual(payload["taxSystem"], 1)

    @override_settings(ALFABANK_RECEIPT_MODE="bank", ALFABANK_TAX_SYSTEM=1)
    def test_new_vat_rates_map_to_documented_bank_codes_for_goods_and_delivery(self):
        for internal, bank in ((7, 10), (8, 12), (9, 11), (10, 13), (11, 14), (12, 15)):
            with self.subTest(vat_code=internal, tax_type=bank):
                self.order.items.update(vat_code=internal)
                self.order.delivery_vat_code = internal
                payload = payment_payload(self.order)
                items = json.loads(payload["orderBundle"])["cartItems"]["items"]
                self.assertEqual([item["tax"]["taxType"] for item in items], [bank, bank])
                self.assertEqual(sum(item["itemAmount"] for item in items), payload["amount"])

    @override_settings(ALFABANK_RECEIPT_MODE="bank", ALFABANK_TAX_SYSTEM=1)
    def test_missing_or_unsupported_receipt_codes_block_payment(self):
        with self.assertRaises(PaymentUnavailable):
            payment_payload(self.order)
        self.order.items.update(vat_code=999)
        with self.assertRaises(PaymentUnavailable):
            payment_payload(self.order)

    def test_notification_failure_keeps_order_and_queue(self):
        with patch("apps.orders.notifications.EmailMultiAlternatives.send", side_effect=OSError("test")):
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
            "apps.payments.management.commands.reconcile_payments.reconcile_attempt",
            side_effect=PaymentUnavailable("offline"),
        ) as reconcile:
            call_command("reconcile_payments", limit=1, verbosity=0)
        reconcile.assert_called_once_with(old.pk)


@override_settings(
    ALFABANK_ENABLED=True,
    ALFABANK_USERNAME="test-merchant",
    ALFABANK_PASSWORD="fake-test-password",
    ALFABANK_TEST_MODE=True,
    ALFABANK_LIVE_APPROVED=False,
    ALFABANK_RECEIPT_MODE="unconfigured",
)
class AlfaProtocolTests(SimpleTestCase):
    def setUp(self):
        self.number = str(uuid.uuid4())
        self.data = {
            "errorCode": "0",
            "orderNumber": self.number,
            "orderStatus": 2,
            "actionCode": 0,
            "amount": 15000,
            "currency": "643",
            "merchantOrderParams": [{"name": "order_id", "value": str(uuid.uuid4())}],
            "attributes": [{"name": "mdOrder", "value": "test-payment-id"}],
            "paymentAmountInfo": {"depositedAmount": 15000, "refundedAmount": 0},
        }

    def parse(self, data=None):
        return VerifiedPayment.parse(data or self.data, account_id="test-merchant", test=True)

    def test_real_extended_status_and_cumulative_refund(self):
        self.assertEqual(self.parse().amount, Decimal("150"))
        self.data["orderStatus"] = 4
        self.data["paymentAmountInfo"]["refundedAmount"] = 4000
        result = self.parse()
        self.assertEqual(result.refunded_amount, Decimal("40"))
        self.assertEqual(result.status, "succeeded")

    def test_partial_and_full_refunds_accept_gross_capture_or_exact_remaining_balance(self):
        for refunded in (4000, 15000):
            for deposited in (15000, 15000 - refunded):
                with self.subTest(refunded=refunded, deposited=deposited):
                    data = {
                        **self.data,
                        "orderStatus": 4,
                        "paymentAmountInfo": {"depositedAmount": deposited, "refundedAmount": refunded},
                    }
                    result = self.parse(data)
                    self.assertTrue(result.paid)
                    self.assertEqual(result.amount, Decimal("150"))
                    self.assertEqual(result.refunded_amount, Decimal(refunded) / 100)

    def test_refund_balance_must_be_complete_and_match_original_amount(self):
        for amounts in (
            {"depositedAmount": 10999, "refundedAmount": 4000},
            {"depositedAmount": 11001, "refundedAmount": 4000},
            {"depositedAmount": 15001, "refundedAmount": 4000},
            {"depositedAmount": 1, "refundedAmount": 15000},
            {"depositedAmount": -1, "refundedAmount": 15000},
            {"refundedAmount": 15000},
        ):
            with self.subTest(amounts=amounts), self.assertRaises(InvalidPayment):
                self.parse({**self.data, "orderStatus": 4, "paymentAmountInfo": amounts})

    def test_all_bank_statuses_and_non_capture_states(self):
        for code, expected in (
            (0, "pending"),
            (1, "waiting_for_capture"),
            (3, "canceled"),
            (5, "pending"),
            (6, "canceled"),
        ):
            with self.subTest(code=code):
                data = {**self.data, "orderStatus": code, "paymentAmountInfo": {}}
                self.assertEqual(self.parse(data).status, expected)
                self.assertFalse(self.parse(data).paid)

    def test_unknown_status_currency_bad_money_capture_and_refund_rejected(self):
        for change in (
            {"orderStatus": 7},
            {"orderStatus": True},
            {"currency": "840"},
            {"currency": 810},
            {"amount": 15000.0},
            {"amount": "NaN"},
            {"amount": -1},
            {"actionCode": 5},
            {"paymentAmountInfo": {}},
            {"paymentAmountInfo": {"depositedAmount": 14999, "refundedAmount": 0}},
            {"paymentAmountInfo": {"depositedAmount": 15000, "refundedAmount": 15001}},
            {"paymentAmountInfo": {"depositedAmount": 15000, "refundedAmount": -1}},
            {"orderStatus": 4},
            {"orderId": "conflicting-id"},
        ):
            with self.subTest(change=change), self.assertRaises(InvalidPayment):
                self.parse({**self.data, **change})

    def test_invalid_metadata_is_not_guessed_from_request(self):
        for change in ({"merchantOrderParams": []}, {"orderNumber": "invalid"}, {"attributes": []}):
            with self.subTest(change=change), self.assertRaises(InvalidPayment):
                self.parse({**self.data, **change})

    def test_register_form_protocol_and_status_are_separate_authenticated_posts(self):
        client = AlfaBankClient()
        responses = [
            {"errorCode": "6"},
            {"orderId": "test-payment-id", "formUrl": bank_url()},
            self.data,
        ]
        client.opener.open = Mock(side_effect=[BytesIO(json.dumps(data).encode()) for data in responses])
        with self.assertRaises(PaymentNotFound):
            client.get_payment(order_number=self.number)
        result = client.create_payment({"orderNumber": self.number, "amount": 15000}, self.number)
        self.assertEqual(result.confirmation_url, bank_url())
        requests = [call.args[0] for call in client.opener.open.call_args_list]
        self.assertEqual(
            [r.full_url.rsplit("/", 1)[1] for r in requests],
            [
                "getOrderStatusExtended.do",
                "register.do",
                "getOrderStatusExtended.do",
            ],
        )
        self.assertTrue(all(r.method == "POST" for r in requests))
        for request in requests:
            self.assertEqual(request.get_header("Content-type"), "application/x-www-form-urlencoded")
            body = parse_qs(request.data.decode())
            self.assertEqual(body["userName"], ["test-merchant"])
            self.assertNotIn("password", request.full_url)
        self.assertEqual(parse_qs(requests[1].data.decode())["amount"], ["15000"])

    def test_registration_timeout_and_duplicate_use_number_lookup(self):
        for registration in (PaymentUnavailable("timeout"), {"errorCode": "1"}):
            client = AlfaBankClient()
            client.request = Mock(side_effect=[registration, self.data])
            client.create_payment({"orderNumber": self.number}, self.number)
            self.assertEqual(
                client.request.call_args.args,
                (
                    "getOrderStatusExtended.do",
                    {"orderNumber": self.number},
                ),
            )
            self.assertEqual(client.request.call_count, 2)

    def test_authentication_error_is_never_treated_as_not_found(self):
        client = AlfaBankClient()
        client.request = Mock(return_value={"errorCode": "5", "errorMessage": "do not display secrets"})
        with self.assertRaises(PaymentUnavailable) as error:
            client.get_payment(order_number=self.number)
        self.assertNotIsInstance(error.exception, PaymentNotFound)
        self.assertNotIn("secrets", str(error.exception))

    def test_redirect_allowlist_is_exact_and_environment_specific(self):
        self.assertEqual(safe_confirmation_url(bank_url(), True, "test-payment-id"), bank_url())
        for url in (
            bank_url(test=False),
            bank_url().replace("https:", "http:"),
            bank_url().replace("alfa.rbsuat.com", "alfa.rbsuat.com.evil.example"),
            bank_url().replace("alfa.rbsuat.com", "user@alfa.rbsuat.com"),
            bank_url().replace("alfa.rbsuat.com", "alfa.rbsuat.com:444"),
            bank_url().replace("test-payment-id", "wrong-id"),
            bank_url() + "&mdOrder=another",
            bank_url().replace("/payment/merchants/", "/redirect/"),
            bank_url() + "#fragment",
        ):
            with self.subTest(url=url), self.assertRaises(InvalidPayment):
                safe_confirmation_url(url, True, "test-payment-id")
        self.assertIsNone(NoRedirect().redirect_request(None, None, 307, "", {}, "https://other.example"))

    def test_live_and_disabled_configuration_fail_closed(self):
        with override_settings(ALFABANK_ENABLED=False), self.assertRaises(PaymentUnavailable):
            AlfaBankClient()
        with override_settings(ALFABANK_TEST_MODE=False), self.assertRaises(PaymentUnavailable):
            AlfaBankClient()
        with (
            override_settings(ALFABANK_TEST_MODE=False, ALFABANK_LIVE_APPROVED=True),
            self.assertRaises(PaymentUnavailable),
        ):
            AlfaBankClient()
        with override_settings(
            ALFABANK_TEST_MODE=False, ALFABANK_LIVE_APPROVED=True, ALFABANK_RECEIPT_MODE="external"
        ):
            self.assertEqual(AlfaBankClient().base_url, "https://pay.alfabank.ru/payment/rest/")

    def test_minor_units_do_not_round_or_accept_floats(self):
        self.assertEqual(minor_units(Decimal("150.01")), 15001)
        for value in (Decimal("1.001"), Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), 1.23, True):
            with self.subTest(value=value), self.assertRaises(InvalidPayment):
                minor_units(value)
