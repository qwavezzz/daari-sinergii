from decimal import Decimal
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from apps.payments.models import PaymentAttempt, TrialPayment
from apps.payments.provider import PaymentUnavailable
from apps.payments.services import start_payment, verify_context
from apps.payments.trial import apply_trial_action
from .cdek import DeliveryUnavailable
from .models import Notification, Order
from .services import QuoteChanged, create_order
from .shipping import quote_delivery, verified_delivery
from .test_cdek import CDEK_SETTINGS, PICKUP
from .test_support import checkout_data, fixture_cart


@override_settings(
    **CDEK_SETTINGS, CDEK_DEMO_QUOTES_ENABLED=True, PAYMENT_STUB_ENABLED=True, ALFABANK_ENABLED=False
)
class DemoDeliveryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(HTTP_HOST="shop.localhost")
        session = self.client.session
        session.save()
        self.cart, self.product, self.method = fixture_cart(session.session_key, quantity=2)
        self.method.type = "cdek_pvz"
        self.method.cdek_tariff_code = 136
        self.method.save()
        self.product.package_weight_g = 450
        self.product.package_length_cm = 20
        self.product.package_width_cm = 10
        self.product.package_height_cm = 8
        self.product.save()
        self.product.confirm_package_measurements()
        self.provider = Mock()
        self.provider.pickup.return_value = dict(PICKUP)
        self.provider.calculate.side_effect = DeliveryUnavailable("Sandbox calculator unavailable")
        boundary = patch("apps.orders.shipping.CdekClient", return_value=self.provider)
        self.boundary = boundary.start()
        self.addCleanup(boundary.stop)

    def quote(self):
        return quote_delivery(self.cart, self.method, "TEST1", self.cart.session_key)

    def data(self, result):
        return checkout_data(
            self.cart,
            self.method,
            quote_token=result["quote_token"],
            delivery_quote=result["delivery_quote"],
            pvz_code="TEST1",
        )

    def test_fixed_price_for_whole_order_preserves_packing_and_has_no_carrier_promise(self):
        result = self.quote()
        snapshot = result["shipping"]
        self.assertEqual(result["total"], "700.00")
        self.assertEqual(snapshot["price_source"], "demo")
        self.assertEqual(snapshot["price"], "500.00")
        self.assertEqual(len(snapshot["packages"]), 2)
        self.assertTrue(snapshot["packing"]["measurements_confirmed"])
        self.assertIsNone(snapshot["period_min"])
        self.assertIsNone(snapshot["period_max"])
        self.assertEqual(snapshot["services"], [])
        self.assertEqual(snapshot["waybill"], "none")
        self.provider.pickup.assert_called_once_with("TEST1")
        self.provider.calculate.assert_not_called()
        self.assertEqual(
            verified_delivery(self.cart, self.method, result["delivery_quote"], "TEST1"), snapshot
        )

    def test_unsafe_settings_refuse_demo_before_calling_carrier(self):
        for settings_change in (
            {"CDEK_TEST_MODE": False},
            {"PAYMENT_STUB_ENABLED": False},
            {"ALFABANK_ENABLED": True},
        ):
            with self.subTest(settings=settings_change), override_settings(**settings_change):
                with self.assertRaises(DeliveryUnavailable):
                    self.quote()
        self.boundary.assert_not_called()

    def test_mode_change_invalidates_signed_quote_in_both_directions(self):
        demo = self.quote()
        for settings_change in (
            {"CDEK_DEMO_QUOTES_ENABLED": False},
            {"CDEK_TEST_MODE": False},
            {"PAYMENT_STUB_ENABLED": False},
            {"ALFABANK_ENABLED": True},
        ):
            with self.subTest(settings=settings_change), override_settings(**settings_change):
                with self.assertRaises(QuoteChanged):
                    verified_delivery(self.cart, self.method, demo["delivery_quote"], "TEST1")
        self.provider.calculate.side_effect = None
        self.provider.calculate.return_value = {"price": "321.40", "period_min": 2, "period_max": 5}
        with override_settings(CDEK_DEMO_QUOTES_ENABLED=False):
            carrier = self.quote()
        with self.assertRaises(QuoteChanged):
            verified_delivery(self.cart, self.method, carrier["delivery_quote"], "TEST1")

    def test_disabled_demo_does_not_hide_carrier_failure(self):
        with override_settings(CDEK_DEMO_QUOTES_ENABLED=False), self.assertRaises(DeliveryUnavailable):
            self.quote()

    def test_demo_still_rejects_unknown_pickup_and_unmeasured_packages(self):
        self.provider.pickup.side_effect = DeliveryUnavailable("Пункт не найден")
        with self.assertRaises(DeliveryUnavailable):
            self.quote()
        self.provider.pickup.side_effect = None
        self.provider.pickup.reset_mock()
        self.product.package_weight_g = None
        self.product.save()
        with self.assertRaises(DeliveryUnavailable):
            self.quote()
        self.provider.pickup.assert_not_called()

    def test_demo_respects_pickup_weight_limit(self):
        self.provider.pickup.return_value = {**PICKUP, "weight_max_g": "100"}
        with self.assertRaises(DeliveryUnavailable):
            self.quote()

    def test_checkout_trial_and_order_keep_labels_and_reject_posted_price(self):
        data = self.data(self.quote())
        data.update(delivery_method=self.method.pk, delivery_price="0.01", total="0.01")
        preview = self.client.post("/checkout/", {**data, "first_name": ""})
        self.assertContains(preview, "это не тариф СДЭК", status_code=422)
        self.assertNotContains(preview, "Ориентировочный срок", status_code=422)
        response = self.client.post("/checkout/", data)
        order = Order.objects.get()
        trial = TrialPayment.objects.get(order=order)
        self.assertRedirects(response, trial.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(order.delivery_price, Decimal("500.00"))
        self.assertEqual(order.total, Decimal("700.00"))
        self.assertTrue(order.is_demo_delivery)
        for url in (trial.get_absolute_url(), order.get_absolute_url()):
            page = self.client.get(url)
            self.assertContains(page, "это не тариф СДЭК")
            self.assertContains(page, "500 ₽")
            self.assertNotContains(page, "None")
        apply_trial_action(order.pk, self.cart.session_key, "success", str(trial.action_key))
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.financial_status, "unpaid")
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(self.product.reserved_stock, 0)
        self.assertFalse(PaymentAttempt.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_persisted_demo_cannot_enter_bank_even_without_trial_marker(self):
        order = create_order(self.cart, self.data(self.quote()), self.cart.session_key)
        TrialPayment.objects.filter(order=order).delete()
        with (
            override_settings(
                CDEK_DEMO_QUOTES_ENABLED=False,
                CDEK_TEST_MODE=False,
                PAYMENT_STUB_ENABLED=False,
                ALFABANK_ENABLED=True,
                ALFABANK_TEST_MODE=False,
            ),
            patch("apps.payments.services.AlfaBankClient") as bank,
        ):
            with self.assertRaisesMessage(PaymentUnavailable, "учебной доставкой"):
                start_payment(order.pk)
            with self.assertRaises(PaymentUnavailable):
                verify_context(Mock(order=order, order_id=order.pk))
            bank.assert_not_called()
            self.assertNotContains(self.client.get(order.get_absolute_url()), "Перейти к оплате")
