import copy
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from cart.models import Cart, CartItem
from cart.services import cart_context, mutate_cart
from catalog.models import Product
from payments.services import payment_payload
from .cdek import CdekClient, DeliveryUnavailable
from .models import Order
from .services import QuoteChanged, create_order, sign_quote
from .shipping import quote_delivery, verified_delivery
from .test_support import checkout_data, fixture_cart


CDEK_SETTINGS = {
    "CDEK_ENABLED": True,
    "CDEK_CLIENT_ID": "test-client",
    "CDEK_CLIENT_SECRET": "test-secret",
    "CDEK_TEST_MODE": True,
    "CDEK_FROM_CITY_CODE": 999,
    "CDEK_QUOTE_TTL_SECONDS": 900,
}
PICKUP = {
    "code": "TEST1",
    "city_code": 123,
    "city": "Тестовый город",
    "address": "Тестовая, 1",
    "name": "ПВЗ",
}


@override_settings(**CDEK_SETTINGS)
class CdekCheckoutTests(TestCase):
    def setUp(self):
        self.cart, self.product, self.method = fixture_cart(quantity=2)
        self.method.type = "cdek_pvz"
        self.method.cdek_tariff_code = 136
        self.method.price = Decimal("0.00")
        self.method.address_required = False
        self.method.save()
        self.product.package_weight_g = 450
        self.product.package_length_cm = 20
        self.product.package_width_cm = 10
        self.product.package_height_cm = 8
        self.product.save()
        self.provider = Mock()
        self.provider.pickup.return_value = copy.deepcopy(PICKUP)
        self.provider.calculate.return_value = {"price": "321.40", "period_min": 2, "period_max": 5}
        self.boundary = patch("orders.shipping.CdekClient", return_value=self.provider)
        self.boundary.start()
        self.addCleanup(self.boundary.stop)

    def quote(self):
        return quote_delivery(self.cart, self.method, "TEST1", self.cart.session_key)

    def data(self, result=None):
        result = result or self.quote()
        return checkout_data(
            self.cart,
            self.method,
            quote_token=result["quote_token"],
            delivery_quote=result["delivery_quote"],
            pvz_code="TEST1",
            address="Forged address",
        )

    def browser(self):
        session = self.client.session
        session.save()
        self.cart.session_key = session.session_key
        self.cart.save()
        return {"delivery_method": self.method.pk, "pvz_code": "TEST1", "quote_token": sign_quote(self.cart)}

    def test_quote_and_order_use_only_verified_price_address_and_packages(self):
        result = self.quote()
        self.assertEqual(result["total"], "521.40")
        self.assertEqual(len(result["shipping"]["packages"]), 2)
        self.provider.calculate.assert_called_once_with(
            136,
            PICKUP,
            [
                {"weight": 450, "length": 20, "width": 10, "height": 8},
                {"weight": 450, "length": 20, "width": 10, "height": 8},
            ],
        )
        data = self.data(result)
        data.update(delivery_price="0.01", total="0.01", tariff_code=9999)
        order = create_order(self.cart, data, self.cart.session_key)
        self.assertEqual(order.total, Decimal("521.40"))
        self.assertEqual(order.delivery_price, Decimal("321.40"))
        self.assertEqual(order.address, "Тестовый город, Тестовая, 1")
        self.assertEqual(order.delivery_snapshot["waybill"], "manual")
        self.assertEqual(order.delivery_snapshot["tariff_code"], 136)
        self.assertEqual(payment_payload(order)["amount"], 52140)
        duplicate = create_order(self.cart, data, self.cart.session_key)
        self.assertEqual(duplicate.pk, order.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.reserved_stock, 2)

    def test_unquoted_shipping_is_never_shown_as_zero_or_final_total(self):
        context = cart_context(self.cart)
        self.assertIsNone(context["cart_delivery_price"])
        self.assertIsNone(context["cart_order_total"])
        with self.assertRaises(QuoteChanged):
            create_order(self.cart, checkout_data(self.cart, self.method), self.cart.session_key)
        self.assertFalse(Order.objects.exists())

    def test_altered_token_and_different_pvz_cannot_create_order(self):
        data = self.data()
        for overrides in ({"delivery_quote": data["delivery_quote"] + "tamper"}, {"pvz_code": "OTHER1"}):
            with self.subTest(overrides=overrides), self.assertRaises(QuoteChanged):
                create_order(self.cart, {**data, **overrides}, self.cart.session_key)
        self.assertFalse(Order.objects.exists())

    def test_expired_quote_requires_recalculation(self):
        data = self.data()
        with patch("django.core.signing.time.time", return_value=10**12), self.assertRaises(QuoteChanged):
            create_order(self.cart, data, self.cart.session_key)

    def test_package_price_quantity_tariff_and_environment_changes_invalidate_quote(self):
        result = self.quote()
        for field, value in (("package_weight_g", 900), ("price", Decimal("101.00"))):
            original = getattr(self.product, field)
            Product.objects.filter(pk=self.product.pk).update(**{field: value})
            with self.subTest(field=field), self.assertRaises(QuoteChanged):
                verified_delivery(self.cart, self.method, result["delivery_quote"], "TEST1")
            Product.objects.filter(pk=self.product.pk).update(**{field: original})
        with override_settings(CDEK_FROM_CITY_CODE=1000), self.assertRaises(QuoteChanged):
            verified_delivery(self.cart, self.method, result["delivery_quote"], "TEST1")
        with override_settings(CDEK_TEST_MODE=False), self.assertRaises(QuoteChanged):
            verified_delivery(self.cart, self.method, result["delivery_quote"], "TEST1")
        self.method.cdek_tariff_code = 137
        with self.assertRaises(QuoteChanged):
            verified_delivery(self.cart, self.method, result["delivery_quote"], "TEST1")
        self.method.cdek_tariff_code = 136
        mutate_cart(self.cart, "update", quantity=1, item_id=self.cart.items.first().pk)
        self.cart.refresh_from_db()
        with self.assertRaises(QuoteChanged):
            verified_delivery(self.cart, self.method, result["delivery_quote"], "TEST1")

    def test_quote_cannot_be_replayed_by_another_cart_or_session(self):
        result = self.quote()
        other = Cart.objects.create(session_key="another-owner")
        CartItem.objects.create(cart=other, product=self.product, quantity=2)
        with self.assertRaises(QuoteChanged):
            verified_delivery(other, self.method, result["delivery_quote"], "TEST1")
        with self.assertRaises(DeliveryUnavailable):
            quote_delivery(self.cart, self.method, "TEST1", "another-owner")

    def test_quote_during_cart_mutation_is_rejected(self):
        def calculate(*args):
            mutate_cart(self.cart, "update", quantity=1, item_id=self.cart.items.first().pk)
            return {"price": "321.40", "period_min": 2, "period_max": 5}

        self.provider.calculate.side_effect = calculate
        with self.assertRaises(QuoteChanged):
            self.quote()

    def test_missing_packages_credentials_tariff_and_provider_failure_fail_closed(self):
        self.product.package_weight_g = None
        self.product.save()
        with self.assertRaisesMessage(DeliveryUnavailable, "упаковка"):
            self.quote()
        self.provider.pickup.assert_not_called()
        self.product.package_weight_g = 450
        self.product.save()
        with override_settings(CDEK_CLIENT_SECRET=""), self.assertRaises(DeliveryUnavailable):
            self.quote()
        self.method.cdek_tariff_code = None
        with self.assertRaises(DeliveryUnavailable):
            self.quote()
        self.method.cdek_tariff_code = 136
        self.provider.calculate.side_effect = DeliveryUnavailable("СДЭК временно недоступен.")
        with self.assertRaises(DeliveryUnavailable):
            self.quote()
        self.assertFalse(Order.objects.exists())

    def test_quote_endpoint_ignores_browser_totals_and_rejects_unsafe_code(self):
        values = self.browser()
        response = self.client.post(
            "/checkout/cdek/quote/",
            {**values, "price": "0.01", "address": "Fake"},
            HTTP_HOST="shop.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["shipping"]["price"], "321.40")
        self.assertNotIn("test-secret", response.content.decode())
        response = self.client.post(
            "/checkout/cdek/quote/", {**values, "pvz_code": "../oauth/token"}, HTTP_HOST="shop.localhost"
        )
        self.assertEqual(response.status_code, 422)

    def test_no_javascript_quote_preserves_contacts_and_shows_verified_total(self):
        values = self.browser()
        initial = self.client.get("/checkout/", HTTP_HOST="shop.localhost")
        values.update(
            {
                "shipping_requote": "1",
                "name": "Сохранённое имя",
                "checkout_key": initial.context["form"]["checkout_key"].value(),
            }
        )
        response = self.client.post("/checkout/", values, HTTP_HOST="shop.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"]["name"].value(), "Сохранённое имя")
        self.assertEqual(response.context["order_total"], Decimal("521.40"))
        self.assertContains(response, "Тестовая, 1")
        self.assertFalse(Order.objects.exists())

    def test_expired_quote_checkout_retains_input_and_clears_payable_total(self):
        self.browser()
        data = self.data()
        data["delivery_method"] = self.method.pk
        with override_settings(CDEK_QUOTE_TTL_SECONDS=-1):
            response = self.client.post("/checkout/", data, HTTP_HOST="shop.localhost")
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "Расчёт доставки устарел", status_code=422)
        self.assertIsNone(response.context["order_total"])
        self.assertEqual(response.context["form"]["name"].value(), data["name"])
        self.assertFalse(Order.objects.exists())

    def test_widget_proxy_only_reads_offices_with_fixed_filter_and_no_secret(self):
        self.browser()
        with patch("orders.cdek.CdekClient") as client:

            def offices(filters, *, response_headers):
                response_headers["X-Total-Elements"] = "0"
                return []

            client.return_value.offices.side_effect = offices
            response = self.client.get(
                "/checkout/cdek/widget/?action=offices&city_code=123&url=https://evil.test&client_secret=evil",
                HTTP_HOST="shop.localhost",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                client.return_value.offices.call_args.args[0], {"city_code": 123, "page": 0, "size": 500}
            )
            self.assertEqual(response["X-Service-Version"], "3.11.1")
            response = self.client.get("/checkout/cdek/widget/?action=calculate", HTTP_HOST="shop.localhost")
            self.assertEqual(response.status_code, 400)

    def test_ajax_quote_rejects_prices_changed_since_page_was_displayed(self):
        values = self.browser()
        Product.objects.filter(pk=self.product.pk).update(price="101.00")
        response = self.client.post("/checkout/cdek/quote/", values, HTTP_HOST="shop.localhost")
        self.assertEqual(response.status_code, 422)
        self.assertIn("Обновите страницу", response.json()["message"])
        self.provider.calculate.assert_not_called()


@override_settings(**CDEK_SETTINGS)
class CdekBoundaryTests(TestCase):
    def test_office_weight_limits_are_enforced_before_calculator(self):
        client = CdekClient()
        pickup = {**PICKUP, "weight_min_g": "0", "weight_max_g": "500"}
        with patch.object(client, "_request") as request, self.assertRaises(DeliveryUnavailable):
            client.calculate(136, pickup, [{"weight": 450}, {"weight": 450}])
        request.assert_not_called()

    def test_pickup_is_verified_from_api_and_disabled_or_foreign_points_rejected(self):
        client = CdekClient()
        office = {
            "code": "TEST1",
            "type": "PVZ",
            "is_handout": True,
            "location": {"city_code": 123, "city": "Город", "address": "Адрес", "country_code": "RU"},
        }
        with patch.object(client, "offices", return_value=[office]):
            self.assertEqual(client.pickup("test1")["address"], "Адрес")
            office["is_handout"] = False
            with self.assertRaises(DeliveryUnavailable):
                client.pickup("TEST1")
            office["is_handout"] = True
            office["location"]["country_code"] = "XX"
            with self.assertRaises(DeliveryUnavailable):
                client.pickup("TEST1")

    def test_calculator_rejects_bad_money_and_missing_or_reversed_duration(self):
        client = CdekClient()
        for data in (
            {"delivery_sum": "NaN", "period_min": 1, "period_max": 2},
            {"delivery_sum": 0, "period_min": 1, "period_max": 2},
            {"delivery_sum": 100, "period_min": 3, "period_max": 2},
            {"delivery_sum": 100, "period_min": 1, "period_max": 2, "currency": "USD"},
            {"delivery_sum": 100},
        ):
            with (
                self.subTest(data=data),
                patch.object(client, "_token", return_value="test-token"),
                patch.object(client, "_request", return_value=data),
                self.assertRaises(DeliveryUnavailable),
            ):
                client.calculate(136, PICKUP, [{"weight": 450}])

    def test_server_origin_tariff_and_packages_are_sent_in_rubles(self):
        client = CdekClient()
        with (
            patch.object(client, "_token", return_value="test-token"),
            patch.object(
                client, "_request", return_value={"delivery_sum": 100, "period_min": 1, "period_max": 2}
            ) as request,
        ):
            self.assertEqual(client.calculate(136, PICKUP, [{"weight": 450}])["price"], "100.00")
            self.assertEqual(request.call_args.kwargs["payload"]["from_location"], {"code": 999})
            self.assertEqual(request.call_args.kwargs["payload"]["tariff_code"], 136)
            self.assertEqual(request.call_args.kwargs["payload"]["currency"], 1)
