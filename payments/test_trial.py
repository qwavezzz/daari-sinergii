from decimal import Decimal
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.models import AuditEntry
from orders.models import Notification, Order, StockReservation
from orders.services import create_order, queue_notification
from orders.test_cdek import CDEK_SETTINGS, PICKUP
from orders.test_support import checkout_data, fixture_cart
from .models import PaymentAttempt, PaymentEvent, Refund, TrialPayment
from .provider import PaymentUnavailable
from .services import reconcile_attempt, start_payment
from .trial import create_trial_payment


@override_settings(PAYMENT_STUB_ENABLED=True, ALFABANK_ENABLED=False)
class TrialPaymentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(HTTP_HOST="shop.localhost")
        session = self.client.session
        session.save()
        self.cart, self.product, self.method = fixture_cart(session.session_key)
        data = checkout_data(self.cart, self.method)
        self.checkout_payload = {**data, "delivery_method": self.method.pk}
        with patch("payments.services.AlfaBankClient") as bank:
            response = self.client.post("/checkout/", self.checkout_payload)
        bank.assert_not_called()
        self.order = Order.objects.get(checkout_key=data["checkout_key"])
        self.trial = TrialPayment.objects.get(order=self.order)
        self.url = self.trial.get_absolute_url()
        self.action_url = reverse(
            "payments:trial_action", args=[self.order.public_id], urlconf="config.shop_urls"
        )
        self.assertRedirects(response, self.url, fetch_redirect_response=False)

    def action(self, action, *, action_key=None, **extra):
        self.trial.refresh_from_db()
        return self.client.post(
            self.action_url,
            {"action": action, "action_key": action_key or str(self.trial.action_key), **extra},
        )

    def assert_no_financial_effects(self):
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.financial_status, "unpaid")
        self.assertIsNone(self.order.paid_attempt_id)
        self.assertEqual(self.order.status, "new")
        self.assertEqual(self.product.stock, 5)
        self.assertFalse(PaymentAttempt.objects.exists())
        self.assertFalse(PaymentEvent.objects.exists())
        self.assertFalse(Refund.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_checkout_shows_saved_components_and_explicit_no_charge_message(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Пробная оплата")
        self.assertContains(response, "Деньги не списываются.")
        self.assertContains(response, "Данные карты не нужны.")
        self.assertContains(response, self.product.name)
        self.assertContains(response, "100 ₽")
        self.assertContains(response, "50 ₽")
        self.assertContains(response, "150 ₽")
        self.assertContains(response, self.method.name)
        self.assertNotContains(response, 'name="card')
        self.assertIn("no-store", response["Cache-Control"])
        self.assertContains(response, 'name="robots" content="noindex, nofollow"')
        self.assert_no_financial_effects()

    def test_success_is_a_rehearsal_releases_reserve_and_is_idempotent(self):
        with patch("payments.services.AlfaBankClient") as bank:
            self.assertRedirects(self.action("success"), self.url, fetch_redirect_response=False)
            self.action("success")
            self.action("cancel")
            self.action("retry")
        bank.assert_not_called()
        self.trial.refresh_from_db()
        self.assertEqual(self.trial.state, "succeeded")
        self.assert_no_financial_effects()
        self.assertEqual(self.product.reserved_stock, 0)
        self.assertEqual(StockReservation.objects.get(order=self.order).state, "released")
        self.assertEqual(AuditEntry.objects.filter(kind="trial_payment.succeeded").count(), 1)
        response = self.client.get(self.url)
        self.assertContains(response, "Проба завершена")
        self.assertContains(response, "Реальная оплата не получена")
        self.assertNotContains(response, 'value="success"')

    def test_cancel_retry_and_stale_submissions_are_safe(self):
        original_key = str(self.trial.action_key)
        self.action("cancel")
        self.assertContains(self.client.get(self.url), "Повторить пробную оплату")
        self.action("success", action_key=original_key)
        self.trial.refresh_from_db()
        self.assertEqual(self.trial.state, "canceled")
        self.action("retry", action_key=original_key)
        self.trial.refresh_from_db()
        self.assertEqual(self.trial.state, "pending")
        new_key = str(self.trial.action_key)
        self.assertNotEqual(new_key, original_key)
        self.action("retry", action_key=original_key)
        self.action("cancel", action_key=original_key)
        self.action("success", action_key=original_key)
        self.trial.refresh_from_db()
        self.assertEqual(self.trial.state, "pending")
        self.assertEqual(str(self.trial.action_key), new_key)
        self.action("success", action_key=new_key)
        self.trial.refresh_from_db()
        self.assertEqual(self.trial.state, "succeeded")
        self.assert_no_financial_effects()
        self.assertEqual(self.product.reserved_stock, 0)

    def test_saved_amounts_do_not_follow_catalog_changes_or_posted_amount(self):
        self.product.name = "Изменённое название"
        self.product.price = Decimal("800.00")
        self.product.save(update_fields=["name", "price"])
        self.method.price = Decimal("900.00")
        self.method.save()
        response = self.client.get(self.url)
        self.assertContains(response, "Тестовый товар")
        self.assertContains(response, "150 ₽")
        self.assertNotContains(response, "800 ₽")
        self.action("success", total="0.01", delivery_price="0.00", financial_status="paid")
        self.trial.refresh_from_db()
        self.assertEqual(Decimal(self.trial.snapshot["total"]), Decimal("150.00"))
        self.assert_no_financial_effects()

    def test_repeated_checkout_does_not_create_another_order_or_trial(self):
        response = self.client.post("/checkout/", self.checkout_payload)
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(TrialPayment.objects.count(), 1)
        self.assert_no_financial_effects()

    def test_foreign_and_missing_sessions_cannot_read_or_modify_trial(self):
        stranger = Client(HTTP_HOST="shop.localhost")
        self.assertEqual(stranger.get(self.url).status_code, 404)
        self.assertEqual(stranger.post(self.action_url, {"action": "success"}).status_code, 404)
        session = stranger.session
        session.save()
        self.assertEqual(stranger.get(self.url).status_code, 404)
        self.assertEqual(
            stranger.post(
                self.action_url, {"action": "success", "action_key": str(self.trial.action_key)}
            ).status_code,
            404,
        )
        self.trial.refresh_from_db()
        self.assertEqual(self.trial.state, "pending")

    def test_csrf_is_required_and_get_does_not_change_state(self):
        protected = Client(enforce_csrf_checks=True, HTTP_HOST="shop.localhost")
        protected.cookies = self.client.cookies
        self.assertEqual(protected.get(self.action_url).status_code, 405)
        self.assertEqual(
            protected.post(
                self.action_url, {"action": "success", "action_key": str(self.trial.action_key)}
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get(self.url, {"action": "success"}).status_code, 200)
        self.trial.refresh_from_db()
        self.assertEqual(self.trial.state, "pending")
        protected.get(self.url)
        response = protected.post(
            self.action_url,
            {
                "action": "success",
                "action_key": str(self.trial.action_key),
                "csrfmiddlewaretoken": protected.cookies["csrftoken"].value,
            },
        )
        self.assertRedirects(response, self.url, fetch_redirect_response=False)

    def test_disabled_feature_hides_all_trial_endpoints_and_cannot_become_bank_order(self):
        with override_settings(PAYMENT_STUB_ENABLED=False, ALFABANK_ENABLED=True):
            self.assertEqual(self.client.get(self.url).status_code, 404)
            self.assertEqual(self.action("success").status_code, 404)
            with patch("payments.services.AlfaBankClient") as bank:
                with self.assertRaises(PaymentUnavailable):
                    start_payment(self.order.pk)
                response = self.client.post(self.order.get_absolute_url() + "pay/")
            bank.assert_not_called()
            self.assertRedirects(response, self.order.get_absolute_url(), fetch_redirect_response=False)
        self.assert_no_financial_effects()

    def test_historical_order_cannot_be_enrolled_through_trial_endpoints(self):
        historical_client = Client(HTTP_HOST="shop.localhost")
        session = historical_client.session
        session.save()
        with override_settings(PAYMENT_STUB_ENABLED=False):
            cart, _, method = fixture_cart(session.session_key)
            historical = create_order(cart, checkout_data(cart, method), cart.session_key)
        url = reverse("payments:trial", args=[historical.public_id], urlconf="config.shop_urls")
        action_url = reverse("payments:trial_action", args=[historical.public_id], urlconf="config.shop_urls")
        self.assertEqual(historical_client.get(url).status_code, 404)
        self.assertEqual(historical_client.post(action_url, {"action": "success"}).status_code, 404)
        historical_client.post(historical.get_absolute_url() + "pay/")
        self.assertFalse(TrialPayment.objects.filter(order=historical).exists())

    def test_bank_reconciliation_rejects_trial_even_with_inconsistent_attempt(self):
        attempt = PaymentAttempt.objects.create(order=self.order, amount=self.order.total)
        with patch("payments.services.AlfaBankClient") as bank:
            with self.assertRaises(PaymentUnavailable):
                reconcile_attempt(attempt.pk)
        bank.assert_not_called()
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "unpaid")

    def test_trial_cannot_be_created_for_an_existing_bank_attempt(self):
        with override_settings(PAYMENT_STUB_ENABLED=False):
            cart, _, method = fixture_cart("bank-order-owner")
            order = create_order(cart, checkout_data(cart, method), cart.session_key)
        PaymentAttempt.objects.create(order=order, amount=order.total)
        with self.assertRaises(ValidationError):
            create_trial_payment(order)
        self.assertFalse(TrialPayment.objects.filter(order=order).exists())

    def test_later_order_notifications_are_suppressed_for_rehearsals(self):
        queue_notification(self.order, "paid")
        queue_notification(self.order, "canceled")
        self.assertFalse(Notification.objects.filter(order=self.order).exists())

    def test_invalid_action_or_missing_key_never_changes_trial(self):
        self.assertEqual(self.action("invalid").status_code, 400)
        self.assertEqual(self.client.post(self.action_url, {"action": "success"}).status_code, 400)
        self.trial.refresh_from_db()
        self.assertEqual(self.trial.state, "pending")
        self.assert_no_financial_effects()

    def test_htmx_uses_same_saved_trial_and_safe_local_redirect(self):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertNotContains(response, "<!doctype html>")
        self.assertContains(response, "Деньги не списываются.")
        response = self.client.post(
            self.action_url,
            {"action": "success", "action_key": str(self.trial.action_key)},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.url, response["HX-Location"])
        self.assert_no_financial_effects()


@override_settings(PAYMENT_STUB_ENABLED=True, ALFABANK_ENABLED=False, **CDEK_SETTINGS)
class CdekTrialCheckoutTests(TestCase):
    def test_verified_cdek_quote_reaches_trial_with_saved_goods_delivery_and_pickup(self):
        cache.clear()
        client = Client(HTTP_HOST="shop.localhost")
        session = client.session
        session.save()
        cart, product, method = fixture_cart(session.session_key, quantity=2)
        product.package_weight_g = 450
        product.package_length_cm = 20
        product.package_width_cm = 10
        product.package_height_cm = 8
        product.save()
        method.type = "cdek_pvz"
        method.cdek_tariff_code = 136
        method.save()
        provider = Mock()
        provider.pickup.return_value = PICKUP.copy()
        provider.calculate.return_value = {"price": "321.40", "period_min": 2, "period_max": 5}
        data = checkout_data(cart, method)
        with patch("orders.shipping.CdekClient", return_value=provider):
            quote = client.post(
                "/checkout/cdek/quote/",
                {
                    "delivery_method": method.pk,
                    "pvz_code": PICKUP["code"],
                    "quote_token": data["quote_token"],
                },
            )
            self.assertEqual(quote.status_code, 200)
            quote = quote.json()
            response = client.post(
                "/checkout/",
                {
                    **data,
                    "delivery_method": method.pk,
                    "pvz_code": PICKUP["code"],
                    "quote_token": quote["quote_token"],
                    "delivery_quote": quote["delivery_quote"],
                    "total": "0.01",
                    "delivery_price": "0.01",
                },
            )
        trial = TrialPayment.objects.select_related("order").get()
        self.assertRedirects(response, trial.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(Decimal(trial.snapshot["subtotal"]), Decimal("200.00"))
        self.assertEqual(Decimal(trial.snapshot["delivery_price"]), Decimal("321.40"))
        self.assertEqual(Decimal(trial.snapshot["total"]), Decimal("521.40"))
        page = client.get(trial.get_absolute_url())
        self.assertContains(page, "200 ₽")
        self.assertContains(page, "321,40 ₽")
        self.assertContains(page, "521,40 ₽")
        self.assertContains(page, "ПВЗ TEST1")
        self.assertContains(page, "Тестовый город, Тестовая, 1")
        self.assertFalse(PaymentAttempt.objects.exists())
        self.assertFalse(Notification.objects.exists())
