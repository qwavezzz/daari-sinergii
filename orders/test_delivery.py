from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from cart.services import cart_context
from content.models import SiteSettings
from orders.test_support import fixture_cart, checkout_data
from orders.services import create_order, QuoteChanged
from payments.services import payment_payload
from payments.provider import PaymentUnavailable


class DeliveryTotalTests(TestCase):
    def setUp(self):
        self.cart, self.product, self.method = fixture_cart()
        self.product.price = Decimal("690.00")
        self.product.vat_code = 1
        self.product.save()
        self.method.price = Decimal("300.00")
        self.method.vat_code = 1
        self.method.is_default = True
        self.method.save()

    def test_690_plus_300_in_cart_order_payment_and_receipt(self):
        context = cart_context(self.cart)
        self.assertEqual(context["cart_total"], Decimal("690.00"))
        self.assertEqual(context["cart_delivery_price"], Decimal("300.00"))
        self.assertEqual(context["cart_order_total"], Decimal("990.00"))
        order = create_order(self.cart, checkout_data(self.cart, self.method), self.cart.session_key)
        with override_settings(YOOKASSA_RECEIPT_MODE="provider"):
            payload = payment_payload(order)
        self.assertEqual(payload["amount"]["value"], "990.00")
        items = payload["receipt"]["items"]
        self.assertEqual(items[1]["payment_subject"], "service")
        self.assertEqual(items[1]["amount"]["value"], "300.00")
        self.assertEqual(
            sum(Decimal(i["amount"]["value"]) * Decimal(i["quantity"]) for i in items), Decimal("990.00")
        )
        self.assertEqual(payload["receipt"]["customer"]["email"], order.email)

    def test_tariff_changes_require_confirmation_and_do_not_change_existing_order(self):
        data = checkout_data(self.cart, self.method)
        self.method.price = Decimal("400.00")
        self.method.save()
        with self.assertRaises(QuoteChanged):
            create_order(self.cart, data, self.cart.session_key)
        self.assertEqual(cart_context(self.cart)["cart_order_total"], Decimal("1090.00"))
        order = create_order(self.cart, checkout_data(self.cart, self.method), self.cart.session_key)
        self.method.price = Decimal("800.00")
        self.method.vat_code = 11
        self.method.save()
        order.refresh_from_db()
        with override_settings(YOOKASSA_RECEIPT_MODE="provider"):
            payload = payment_payload(order)
        self.assertEqual(payload["amount"]["value"], "1090.00")
        self.assertEqual(payload["receipt"]["items"][-1]["vat_code"], 1)

    def test_multiple_items_pay_one_delivery_and_empty_cart_pays_none(self):
        self.cart.items.update(quantity=3)
        self.assertEqual(cart_context(self.cart)["cart_order_total"], Decimal("2370.00"))
        self.cart.items.all().delete()
        self.assertEqual(cart_context(self.cart)["cart_order_total"], Decimal("0.00"))
        self.assertEqual(cart_context(self.cart)["cart_delivery_price"], Decimal("0.00"))

    def test_free_delivery_omits_receipt_line_and_unknown_tax_fails_closed(self):
        self.method.vat_code = None
        self.method.save()
        order = create_order(self.cart, checkout_data(self.cart, self.method), self.cart.session_key)
        with override_settings(YOOKASSA_RECEIPT_MODE="provider"), self.assertRaises(PaymentUnavailable):
            payment_payload(order)
        order.delivery_price = Decimal("0.00")
        order.total = order.subtotal
        with override_settings(YOOKASSA_RECEIPT_MODE="provider"):
            self.assertEqual(len(payment_payload(order)["receipt"]["items"]), 1)

    def test_delivery_cannot_be_negative(self):
        self.method.price = Decimal("-1.00")
        with self.assertRaises(ValidationError):
            self.method.full_clean()

    def test_seller_change_requires_confirmation_and_identity_is_snapshotted(self):
        site = SiteSettings.objects.create(legal_name="ИП Тестовый продавец", inn="123456789012")
        data = checkout_data(self.cart, self.method)
        site.inn = "987654321012"
        site.save()
        with self.assertRaises(QuoteChanged):
            create_order(self.cart, data, self.cart.session_key)
        order = create_order(self.cart, checkout_data(self.cart, self.method), self.cart.session_key)
        self.assertIn(site.inn, order.terms_snapshot)

    def test_checkout_displays_default_total_and_requires_pickup_address(self):
        session = self.client.session
        session.save()
        self.cart.session_key = session.session_key
        self.cart.save()
        self.method.address_required = True
        self.method.save()
        response = self.client.get("/checkout/", HTTP_HOST="shop.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["order_total"], Decimal("990.00"))
        self.assertContains(response, 'name="address"')
        response = self.client.get("/cart/", HTTP_HOST="shop.localhost")
        self.assertContains(response, "990")
        self.assertContains(response, "Доставка")
        self.assertEqual(response.context["cart_delivery_price"], Decimal("300.00"))
