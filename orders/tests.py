from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import Mock, patch
from django.contrib.admin.sites import AdminSite
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import (
    Client,
    RequestFactory,
    TestCase,
    TransactionTestCase,
    override_settings,
    skipUnlessDBFeature,
)
from payments.models import PaymentAttempt
from payments.provider import PaymentUnavailable, VerifiedPayment
from catalog.admin import ProductAdmin, ProductAdminForm
from catalog.models import Product
from cart.models import Cart, CartItem
from .models import Order, StoreSettings
from .admin import OrderAdmin
from .services import QuoteChanged, checkout_snapshot, create_order, transition_order
from .test_support import checkout_data, fixture_cart


class OrderTests(TestCase):
    def setUp(self):
        self.cart, self.product, self.method = fixture_cart()

    def create(self, **overrides):
        return create_order(
            self.cart, checkout_data(self.cart, self.method, **overrides), self.cart.session_key
        )

    def test_checkout_is_idempotent_and_snapshots_survive_catalog_changes(self):
        data = checkout_data(self.cart, self.method)
        first = create_order(self.cart, data, self.cart.session_key)
        second = create_order(self.cart, data, self.cart.session_key)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.product.name, self.product.price = "Новое имя", Decimal("999.00")
        self.product.save()
        self.assertEqual(first.items.get().name, "Тестовый товар")
        self.assertEqual(first.items.get().unit_price, 100)
        self.assertEqual(first.total, 150)

    def test_price_change_requires_reconfirmation_and_reserves_nothing(self):
        data = checkout_data(self.cart, self.method)
        Product.objects.filter(pk=self.product.pk).update(price=200)
        with self.assertRaises(QuoteChanged):
            create_order(self.cart, data, self.cart.session_key)
        self.assertFalse(Order.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.reserved_stock, 0)

    def test_legal_change_invalidates_quote(self):
        data = checkout_data(self.cart, self.method)
        StoreSettings.objects.filter(pk=1).update(terms_text="Новые условия")
        with self.assertRaises(QuoteChanged):
            create_order(self.cart, data, self.cart.session_key)

    def test_quote_signature_matches_displayed_amounts(self):
        snapshot, token = checkout_snapshot(self.cart)
        payload = signing.loads(token, salt="checkout-quote")
        self.assertEqual(Decimal(payload["items"][0][2]), snapshot["cart_items"][0]["unit_price"])
        self.assertEqual(Decimal(payload["delivery"][0][1]), snapshot["delivery_quotes"][self.method.pk])

    def test_insufficient_stock_and_empty_cart_are_rejected(self):
        Product.objects.filter(pk=self.product.pk).update(stock=0)
        with self.assertRaises(ValidationError):
            self.create()
        self.cart.items.all().delete()
        with self.assertRaises(ValidationError):
            self.create()

    def test_checkout_gate_requires_terms_and_configured_method(self):
        StoreSettings.objects.filter(pk=1).update(privacy_text="")
        with self.assertRaises(ValidationError):
            self.create()

    def test_order_uuid_alone_does_not_grant_access_in_full_or_partial_response(self):
        order = self.create()
        for extra in ({}, {"HTTP_HX_REQUEST": "true"}):
            self.assertEqual(
                self.client.get(order.get_absolute_url(), HTTP_HOST="shop.localhost", **extra).status_code,
                404,
            )

    def test_browser_return_does_not_confirm_payment(self):
        client = Client(HTTP_HOST="shop.localhost")
        session = client.session
        session.save()
        self.cart.session_key = session.session_key
        self.cart.save()
        order = self.create()
        response = client.get(order.get_absolute_url() + "?status=succeeded&paid=true")
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.financial_status, "unpaid")

    def test_unpaid_order_cannot_be_dispatched(self):
        order = self.create()
        transition_order(order.pk, "processing")
        with self.assertRaises(ValidationError):
            transition_order(order.pk, "ready")

    def test_product_admin_cannot_overwrite_live_reservations_or_consumed_stock(self):
        stale = Product.objects.get(pk=self.product.pk)
        Product.objects.filter(pk=self.product.pk).update(stock=3, reserved_stock=2)
        stale.name = "Редактор исправил название"
        request = RequestFactory().post("/")
        request.user = Mock(pk=1)
        ProductAdmin(Product, AdminSite()).save_model(request, stale, Mock(changed_data=["name"]), True)
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.reserved_stock), (3, 2))

    def test_stale_stock_form_rejected_instead_of_resurrecting_inventory(self):
        old = signing.dumps([self.product.pk, 5, 0], salt="admin-stock")
        Product.objects.filter(pk=self.product.pk).update(stock=2)
        current = Product.objects.get(pk=self.product.pk)
        form = ProductAdminForm(
            data={
                "name": current.name,
                "slug": current.slug,
                "sku": current.sku,
                "price": "100",
                "status": "published",
                "purchasable": True,
                "stock": "5",
                "sort_order": 0,
                "stock_snapshot": old,
            },
            instance=current,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Остаток или резерв изменился", str(form.non_field_errors()))

    def test_admin_does_not_expose_guest_session_credentials(self):
        order = self.create()
        request = RequestFactory().get("/")
        request.user = Mock(is_superuser=True)
        fields = OrderAdmin(Order, AdminSite()).get_fields(request, order)
        self.assertNotIn("session_key", fields)
        self.assertNotIn("checkout_key", fields)

    def test_fully_refunded_ready_order_can_be_canceled(self):
        order = self.create()
        Order.objects.filter(pk=order.pk).update(status="ready", financial_status="refunded")
        transition_order(order.pk, "canceled")
        order.refresh_from_db()
        self.assertEqual(order.status, "canceled")

    def checkout_client(self):
        client = Client(HTTP_HOST="shop.localhost")
        session = client.session
        session.save()
        self.cart.session_key = session.session_key
        self.cart.save(update_fields=["session_key"])
        values = checkout_data(self.cart, self.method)
        values["delivery_method"] = self.method.pk
        values["confirmed_delivery"] = ""
        return client, values

    def test_no_js_checkout_shows_delivery_total_before_creating_order(self):
        client, values = self.checkout_client()
        preview = client.post("/checkout/", values)
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(preview.context["order_total"], 150)
        self.assertEqual(str(preview.context["form"]["confirmed_delivery"].value()), str(self.method.pk))
        values["confirmed_delivery"] = self.method.pk
        complete = client.post("/checkout/", values)
        self.assertEqual(complete.status_code, 302)
        duplicate = client.post("/checkout/", values)
        self.assertEqual(duplicate.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)

    def test_requote_never_creates_order_and_preserves_entered_values(self):
        client, values = self.checkout_client()
        values.update({"requote": "1", "name": "Сохранённое имя", "confirmed_delivery": self.method.pk})
        response = client.post("/checkout/", values, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(response.context["form"]["name"].value(), "Сохранённое имя")
        self.assertEqual(response.context["order_total"], 150)

    def test_price_change_response_shows_same_amount_as_new_signature(self):
        client, values = self.checkout_client()
        values["confirmed_delivery"] = self.method.pk
        Product.objects.filter(pk=self.product.pk).update(price=200)
        response = client.post("/checkout/", values, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.context["order_total"], 250)
        token = response.context["form"]["quote_token"].value()
        self.assertEqual(Decimal(signing.loads(token, salt="checkout-quote")["items"][0][2]), 200)
        self.assertFalse(Order.objects.exists())

    def checkout_provider(self, fail_first=False):
        provider = Mock()
        calls = []

        def create_payment(payload, key):
            calls.append((payload, key))
            if fail_first and len(calls) == 1:
                raise PaymentUnavailable("Платёж пока не подтверждён. Проверка продолжится автоматически.")
            result = VerifiedPayment(
                "checkout-payment-id",
                "pending",
                Decimal(payload["amount"]["value"]),
                "RUB",
                payload["metadata"]["order_id"],
                "test-shop",
                True,
                False,
                "https://yookassa.ru/checkout/test",
            )
            provider.get_payment.return_value = result
            return result

        provider.create_payment.side_effect = create_payment
        return provider, calls

    @override_settings(YOOKASSA_ENABLED=True, YOOKASSA_SHOP_ID="test-shop", YOOKASSA_TEST_MODE=True)
    def test_enabled_checkout_redirects_directly_to_persisted_provider_payment(self):
        client, values = self.checkout_client()
        values["confirmed_delivery"] = self.method.pk
        provider, calls = self.checkout_provider()
        with patch("payments.services.YooKassaClient", return_value=provider):
            response = client.post("/checkout/", values)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://yookassa.ru/checkout/test")
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(PaymentAttempt.objects.get().provider_id, "checkout-payment-id")
        self.assertEqual(len(calls), 1)

    @override_settings(YOOKASSA_ENABLED=True, YOOKASSA_SHOP_ID="test-shop", YOOKASSA_TEST_MODE=True)
    def test_enabled_htmx_checkout_uses_full_external_redirect(self):
        client, values = self.checkout_client()
        values["confirmed_delivery"] = self.method.pk
        provider, _ = self.checkout_provider()
        with patch("payments.services.YooKassaClient", return_value=provider):
            response = client.post("/checkout/", values, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Redirect"], "https://yookassa.ru/checkout/test")
        self.assertNotIn("HX-Location", response.headers)
        self.assertIn('"count": 0', response["HX-Trigger"])

    @override_settings(YOOKASSA_ENABLED=True, YOOKASSA_SHOP_ID="test-shop", YOOKASSA_TEST_MODE=True)
    def test_checkout_payment_timeout_keeps_order_and_retry_reuses_same_operation(self):
        client, values = self.checkout_client()
        values["confirmed_delivery"] = self.method.pk
        provider, calls = self.checkout_provider(fail_first=True)
        with patch("payments.services.YooKassaClient", return_value=provider):
            response = client.post("/checkout/", values)
            order = Order.objects.get()
            self.assertEqual(response["Location"], order.get_absolute_url())
            self.assertEqual(PaymentAttempt.objects.get().state, "unknown")
            status_page = client.get(order.get_absolute_url())
            self.assertContains(status_page, "Платёж пока не подтверждён")
            retry = client.post("/checkout/", values)
            duplicate = client.post("/checkout/", values)
        self.assertEqual(retry["Location"], "https://yookassa.ru/checkout/test")
        self.assertEqual(duplicate["Location"], retry["Location"])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(PaymentAttempt.objects.count(), 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])
        self.product.refresh_from_db()
        self.assertEqual(self.product.reserved_stock, 1)

    @override_settings(YOOKASSA_ENABLED=True)
    def test_order_attention_shows_safe_copy_without_internal_reason_or_payment_button(self):
        client, _ = self.checkout_client()
        order = self.create()
        Order.objects.filter(pk=order.pk).update(
            needs_attention=True, attention_reason="internal-financial-anomaly-detail"
        )
        response = client.get(order.get_absolute_url())
        self.assertContains(response, "Проверяем состояние оплаты")
        self.assertNotContains(response, "internal-financial-anomaly-detail")
        self.assertNotContains(response, "Перейти к оплате")


class ConcurrentCheckoutTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_two_buyers_cannot_reserve_last_unit(self):
        cart, product, method = fixture_cart(stock=1)
        second = Cart.objects.create(session_key="other-owner")
        CartItem.objects.create(cart=second, product=product, quantity=1)
        data = [
            (cart.pk, checkout_data(cart, method), cart.session_key),
            (second.pk, checkout_data(second, method), second.session_key),
        ]

        def purchase(args):
            close_old_connections()
            cart_id, values, key = args
            try:
                create_order(Cart.objects.get(pk=cart_id), values, key)
                return True
            except ValidationError:
                return False
            finally:
                # These worker threads own persistent PostgreSQL connections;
                # request-age cleanup does not close healthy connections.
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(purchase, data))
        self.assertEqual(sum(results), 1)
        product.refresh_from_db()
        self.assertEqual(product.reserved_stock, 1)
