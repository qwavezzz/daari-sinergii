import copy
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.catalog.models import Product
from apps.orders.admin import OrderAdmin
from apps.orders.cdek import DeliveryUnavailable
from apps.orders.models import Order, PackingBox, PackingRecipe, PackingRecipeItem
from apps.orders.services import QuoteChanged, create_order, sign_quote
from apps.orders.shipping import quote_delivery, verified_delivery
from apps.orders.test_cdek import CDEK_SETTINGS, PICKUP
from apps.orders.test_support import checkout_data, fixture_cart


@override_settings(**CDEK_SETTINGS)
class MeasuredPackingCheckoutTests(TestCase):
    def setUp(self):
        self.cart, self.product, self.method = fixture_cart(quantity=3, stock=20)
        self.method.type = "cdek_pvz"
        self.method.cdek_tariff_code = 136
        self.method.save()
        self.product.shipping_mode = "combined"
        self.product.unit_weight_g = 300
        self.product.unit_length_mm = 50
        self.product.unit_width_mm = 50
        self.product.unit_height_mm = 100
        self.product.save()
        self.box = PackingBox.objects.create(
            name="Измеренная тестовая коробка",
            code="test-measured",
            inner_length_mm=180,
            inner_width_mm=100,
            inner_height_mm=120,
            outer_length_mm=187,
            outer_width_mm=108,
            outer_height_mm=128,
            tare_weight_g=70,
            max_weight_g=5000,
        )
        self.recipe = PackingRecipe.objects.create(
            name="Три тестовых флакона",
            box=self.box,
            packing_weight_g=30,
            measured_weight_g=1021,
            outer_length_mm=187,
            outer_width_mm=108,
            outer_height_mm=128,
            instructions="Поставить вертикально в один ряд. Разделить вставками.",
            active=True,
        )
        self.row = PackingRecipeItem.objects.create(recipe=self.recipe, product=self.product, quantity=3)
        self.recipe.confirm_measurements()
        self.provider = Mock()
        self.provider.pickup.return_value = copy.deepcopy(PICKUP)
        self.provider.calculate.return_value = {"price": "321.40", "period_min": 2, "period_max": 5}
        boundary = patch("apps.orders.shipping.CdekClient", return_value=self.provider)
        boundary.start()
        self.addCleanup(boundary.stop)

    def quote(self):
        return quote_delivery(self.cart, self.method, "TEST1", self.cart.session_key)

    def order(self, result):
        return create_order(
            self.cart,
            checkout_data(
                self.cart,
                self.method,
                quote_token=result["quote_token"],
                delivery_quote=result["delivery_quote"],
                pvz_code="TEST1",
            ),
            self.cart.session_key,
        )

    def test_measured_cart_goes_to_carrier_as_one_box_with_declared_value_and_saved_instructions(self):
        result = self.quote()
        self.provider.calculate.assert_called_once_with(
            136,
            PICKUP,
            [{"weight": 1021, "length": 19, "width": 11, "height": 13}],
            declared_value=Decimal("300.00"),
        )
        self.assertEqual(result["total"], "621.40")
        self.assertEqual(result["shipping"]["declared_value"], "300.00")
        self.assertEqual(result["shipping"]["services"], [{"code": "INSURANCE", "parameter": "300.00"}])
        order = self.order(result)
        self.assertEqual(order.delivery_snapshot, result["shipping"])
        self.assertEqual(order.delivery_snapshot["packing"]["parcels"][0]["contents"][0]["quantity"], 3)
        self.assertEqual(order.total, Decimal("621.40"))
        # Operational data is an order snapshot, unaffected by later catalogue edits.
        PackingRecipe.objects.filter(pk=self.recipe.pk).update(instructions="Новая инструкция")
        Product.objects.filter(pk=self.product.pk).update(name="Новое имя", unit_weight_g=310)
        order.refresh_from_db()
        instructions = str(OrderAdmin(Order, admin.site).packing_instructions(order))
        self.assertIn("Поставить вертикально в один ряд", instructions)
        self.assertIn("1021", instructions)
        self.assertIn("187", instructions)
        self.assertNotIn("Новая инструкция", instructions)
        self.assertNotIn("Новое имя", instructions)

    def test_approved_measured_plan_is_available_in_live_mode(self):
        with override_settings(CDEK_TEST_MODE=False):
            result = self.quote()
            self.assertTrue(result["shipping"]["packing"]["measurements_confirmed"])
            self.assertFalse(result["shipping"]["test_mode"])
            self.assertEqual(
                verified_delivery(self.cart, self.method, result["delivery_quote"], "TEST1"),
                result["shipping"],
            )

    def test_every_measurement_or_rule_change_invalidates_a_previous_quote(self):
        result = self.quote()
        for model, instance, field, replacement in (
            (PackingBox, self.box, "tare_weight_g", 71),
            (PackingBox, self.box, "active", False),
            (PackingRecipe, self.recipe, "measured_weight_g", 1022),
            (PackingRecipe, self.recipe, "instructions", "Изменена сборка"),
            (PackingRecipe, self.recipe, "active", False),
            (PackingRecipe, self.recipe, "measurement_signature", ""),
            (PackingRecipeItem, self.row, "quantity", 2),
            (Product, self.product, "unit_height_mm", 101),
            (Product, self.product, "shipping_mode", "individual"),
        ):
            old = getattr(instance, field)
            model.objects.filter(pk=instance.pk).update(**{field: replacement})
            with self.subTest(field=field, model=model.__name__), self.assertRaises(QuoteChanged):
                verified_delivery(self.cart, self.method, result["delivery_quote"], "TEST1")
            model.objects.filter(pk=instance.pk).update(**{field: old})

    def test_configuration_change_while_carrier_calculates_rejects_quote(self):
        def changed(*args, **kwargs):
            PackingBox.objects.filter(pk=self.box.pk).update(outer_length_mm=188)
            return {"price": "321.40", "period_min": 2, "period_max": 5}

        self.provider.calculate.side_effect = changed
        with self.assertRaises(QuoteChanged):
            self.quote()
        self.assertFalse(Order.objects.exists())

    def test_selected_pickup_replans_heavy_box_into_admissible_lighter_boxes(self):
        small = PackingRecipe.objects.create(
            name="Один флакон",
            box=self.box,
            packing_weight_g=30,
            measured_weight_g=421,
            outer_length_mm=187,
            outer_width_mm=108,
            outer_height_mm=128,
            instructions="Один флакон вертикально с защитой.",
            active=True,
        )
        PackingRecipeItem.objects.create(recipe=small, product=self.product, quantity=1)
        small.confirm_measurements()
        self.provider.pickup.return_value = {**PICKUP, "weight_max_g": "500"}
        result = self.quote()
        self.assertEqual(len(result["shipping"]["packages"]), 3)
        self.assertEqual([box["weight"] for box in result["shipping"]["packages"]], [421, 421, 421])
        self.assertEqual(self.provider.calculate.call_args.args[2], result["shipping"]["packages"])

    def test_revoked_individual_confirmation_date_invalidates_existing_live_quote(self):
        self.product.shipping_mode = "individual"
        self.product.package_weight_g = 450
        self.product.package_length_cm = 20
        self.product.package_width_cm = 10
        self.product.package_height_cm = 8
        self.product.save()
        self.product.confirm_package_measurements()
        # An individual product must be protected even outside any recipe fingerprint.
        self.recipe.delete()
        with override_settings(CDEK_TEST_MODE=False):
            result = self.quote()
            Product.objects.filter(pk=self.product.pk).update(package_measured_at=None)
            with self.assertRaises(QuoteChanged):
                verified_delivery(self.cart, self.method, result["delivery_quote"], "TEST1")

    def test_unconfirmed_or_uncovered_combination_never_calls_carrier(self):
        PackingRecipe.objects.filter(pk=self.recipe.pk).update(measurement_signature="")
        with self.assertRaises(DeliveryUnavailable):
            self.quote()
        self.provider.pickup.assert_not_called()
        self.provider.calculate.assert_not_called()

    def test_browser_cannot_choose_a_lighter_parcel_or_lower_declared_value(self):
        session = self.client.session
        session.save()
        self.cart.session_key = session.session_key
        self.cart.save()
        response = self.client.post(
            "/checkout/cdek/quote/",
            {
                "delivery_method": self.method.pk,
                "pvz_code": "TEST1",
                "quote_token": sign_quote(self.cart),
                "packages": "[]",
                "declared_value": "0.01",
                "weight": 1,
                "price": "0.01",
            },
            HTTP_HOST="shop.localhost",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["shipping"]
        self.assertEqual(data["packages"][0]["weight"], 1021)
        self.assertEqual(data["declared_value"], "300.00")

    def test_packing_instructions_escape_catalogue_content(self):
        self.recipe.instructions = '<script>alert("x")</script>'
        self.recipe.save()
        self.recipe.confirm_measurements()
        order = self.order(self.quote())
        html = str(OrderAdmin(Order, admin.site).packing_instructions(order))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_manager_can_manage_packaging_and_read_order_plan(self):
        from django.contrib.auth.models import Group

        call_command("setup_roles", verbosity=0)
        manager = get_user_model().objects.create_user("packing-manager", is_staff=True)
        manager.groups.add(Group.objects.get(name="Менеджер магазина"))
        self.client.force_login(manager)
        for path in ("packingbox", "packingrecipe"):
            response = self.client.get(f"/admin/orders/{path}/", HTTP_HOST="shop.localhost")
            self.assertEqual(response.status_code, 200)
        order = self.order(self.quote())
        response = self.client.get(f"/admin/orders/order/{order.pk}/change/", HTTP_HOST="shop.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Поставить вертикально в один ряд")
        self.assertContains(response, "Объявленная стоимость для накладной СДЭК")
