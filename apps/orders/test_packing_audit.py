"""Regressions for measured packing and carrier selection found in the audit."""

from copy import deepcopy
from decimal import Decimal
from itertools import combinations_with_replacement
from unittest.mock import Mock, patch

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.cart.models import CartItem
from apps.catalog.models import Product

from .cdek import DeliveryUnavailable, TariffUnavailable
from .models import Order, PackingBox, PackingRecipe
from .packing import packing_plan
from .services import QuoteChanged, create_order
from .shipping import quote_delivery, verified_delivery
from .test_cdek import CDEK_SETTINGS, PICKUP
from .test_support import checkout_data, fixture_cart


@override_settings(**{**CDEK_SETTINGS, "CDEK_TEST_MODE": False})
class PackingAuditRegressions(TestCase):
    def setUp(self):
        self.cart, self.product, self.method = fixture_cart(quantity=2, stock=20)
        self.method.type = "cdek_pvz"
        self.method.cdek_tariff_code = 136
        self.method.save()
        self.product.shipping_mode = "combined"
        self.product.unit_weight_g = 100
        self.product.unit_length_mm = 20
        self.product.unit_width_mm = 20
        self.product.unit_height_mm = 30
        self.product.save()
        self.box = PackingBox.objects.create(
            name="Проверенная коробка",
            code="audit-box",
            inner_length_mm=190,
            inner_width_mm=140,
            inner_height_mm=90,
            outer_length_mm=200,
            outer_width_mm=150,
            outer_height_mm=100,
            tare_weight_g=50,
            max_weight_g=10000,
        )
        self.provider = Mock()
        self.provider.pickup.return_value = deepcopy(PICKUP)
        self.provider.calculate.return_value = self.price("225.00")
        boundary = patch("apps.orders.shipping.CdekClient", return_value=self.provider)
        boundary.start()
        self.addCleanup(boundary.stop)

    @staticmethod
    def price(value):
        return {"price": value, "period_min": 2, "period_max": 5}

    def recipe(self, quantity=2, *, product=None, **overrides):
        recipe = PackingRecipe.objects.create(
            **{
                "name": f"Измеренная схема {PackingRecipe.objects.count() + 1}",
                "box": self.box,
                "packing_weight_g": 20,
                "measured_weight_g": 1000,
                "outer_length_mm": 300,
                "outer_width_mm": 200,
                "outer_height_mm": 200,
                "instructions": "Каждый товар защитить и закрепить в коробке.",
                "active": True,
                **overrides,
            }
        )
        recipe.items.create(product=product or self.product, quantity=quantity)
        recipe.confirm_measurements()
        return recipe

    def alternative_plans(self):
        large = self.recipe(
            measured_weight_g=2000,
            outer_length_mm=800,
            outer_width_mm=600,
            outer_height_mm=400,
        )
        small = self.recipe(quantity=1)
        return large, small

    def other_product(self):
        return Product.objects.create(
            name="Другой товар",
            sku="AUDIT-OTHER",
            slug="audit-other",
            price="100.00",
            shipping_mode="combined",
            unit_weight_g=100,
            unit_length_mm=20,
            unit_width_mm=20,
            unit_height_mm=30,
        )

    def quote(self):
        return quote_delivery(self.cart, self.method, "TEST1", self.cart.session_key)

    def verify(self, result):
        return verified_delivery(self.cart, self.method, result["delivery_quote"], "TEST1")

    def test_preferred_plan_uses_volume_after_rounding_for_carrier(self):
        self.recipe(outer_length_mm=501, outer_width_mm=501, outer_height_mm=501)
        better = self.recipe(outer_length_mm=500, outer_width_mm=500, outer_height_mm=504)
        plan = packing_plan(self.cart)
        self.assertEqual(plan["parcels"][0]["recipe_id"], better.pk)
        self.assertEqual(plan["packages"], [{"weight": 1000, "length": 50, "width": 50, "height": 51}])
        self.assertEqual(plan["parcels"][0]["dimensions_mm"]["height"], 504)

    def test_options_keep_different_parcels_for_the_same_composition(self):
        from .packing import packing_options

        compact = self.recipe()
        larger = self.recipe(outer_length_mm=500)
        options = packing_options(self.cart)
        self.assertEqual(
            {tuple(row["recipe_id"] for row in plan["parcels"]) for plan in options},
            {(compact.pk,), (larger.pk,)},
        )

    def test_options_are_bounded_deterministic_and_preserve_exact_contents(self):
        from .packing import packing_options

        self.alternative_plans()
        self.recipe(outer_length_mm=350)
        plans = packing_options(self.cart, limit=2)
        self.assertEqual(len(plans), 2)
        self.assertEqual(plans, packing_options(self.cart, limit=2))
        for plan in plans:
            contents = [item for parcel in plan["parcels"] for item in parcel["contents"]]
            self.assertEqual({item["product_id"] for item in contents}, {self.product.pk})
            self.assertEqual(sum(item["quantity"] for item in contents), 2)
            self.assertTrue(plan["measurements_confirmed"])

    def test_live_individual_measurements_cannot_be_bypassed_by_caller_test_flag(self):
        self.product.shipping_mode = "individual"
        self.product.package_weight_g = 350
        self.product.package_length_cm = 20
        self.product.package_width_cm = 10
        self.product.package_height_cm = 8
        self.product.save()
        with self.assertRaises(DeliveryUnavailable):
            packing_plan(self.cart, test_mode=True)

    def test_options_match_independent_enumeration_for_small_mixed_cart(self):
        from .packing import packing_options

        other = self.other_product()
        CartItem.objects.create(cart=self.cart, product=other, quantity=2)
        mixed = self.recipe(quantity=1, outer_length_mm=340)
        mixed.items.create(product=other, quantity=1)
        mixed.confirm_measurements()
        arrangements = [
            (1, 0, self.recipe(quantity=1, outer_length_mm=300)),
            (2, 0, self.recipe(quantity=2, outer_length_mm=310)),
            (0, 1, self.recipe(quantity=1, product=other, outer_length_mm=320)),
            (0, 2, self.recipe(quantity=2, product=other, outer_length_mm=330)),
            (1, 1, mixed),
        ]
        expected = set()
        for count in range(1, 5):
            for choice in combinations_with_replacement(arrangements, count):
                if sum(row[0] for row in choice) == 2 and sum(row[1] for row in choice) == 2:
                    expected.add(tuple(sorted(row[2].pk for row in choice)))
        self.assertEqual(len(expected), 6)
        plans = packing_options(self.cart, limit=8)
        actual = {tuple(sorted(parcel["recipe_id"] for parcel in plan["parcels"])) for plan in plans}
        self.assertEqual(actual, expected)

    def test_candidate_validation_has_constant_database_query_count(self):
        self.recipe()
        with CaptureQueriesContext(connection) as baseline:
            packing_plan(self.cart)
        for extra in range(24):
            self.recipe(outer_length_mm=310 + extra)
        with CaptureQueriesContext(connection) as expanded:
            packing_plan(self.cart)
        self.assertLessEqual(len(expanded), len(baseline) + 4)
        self.assertLessEqual(len(expanded), 15)

    def test_tariff_refusal_of_large_box_tries_confirmed_split_plan(self):
        _, small = self.alternative_plans()

        def calculate(tariff, pickup, packages, *, declared_value):
            self.assertEqual(declared_value, Decimal("200.00"))
            if len(packages) == 1:
                raise TariffUnavailable("Выбранный тариф недоступен для этой упаковки.")
            return self.price("225.00")

        self.provider.calculate.side_effect = calculate
        result = self.quote()
        self.assertEqual(self.provider.calculate.call_count, 2)
        self.assertEqual(result["shipping"]["price"], "225.00")
        self.assertEqual(
            [parcel["recipe_id"] for parcel in result["shipping"]["packing"]["parcels"]],
            [small.pk, small.pk],
        )
        self.assertEqual(self.verify(result), result["shipping"])

    def test_calculator_price_can_choose_more_parcels_and_is_saved_with_that_plan(self):
        _, small = self.alternative_plans()

        def calculate(tariff, pickup, packages, *, declared_value):
            return self.price("600.00" if len(packages) == 1 else "225.00")

        self.provider.calculate.side_effect = calculate
        result = self.quote()
        self.assertEqual(self.provider.calculate.call_count, 2)
        self.assertEqual(result["total"], "425.00")
        self.assertEqual(result["shipping"]["price"], "225.00")
        order = create_order(
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
        self.assertEqual(order.delivery_snapshot, result["shipping"])
        self.assertEqual(order.delivery_price, Decimal("225.00"))
        self.assertEqual(
            [parcel["recipe_id"] for parcel in order.delivery_snapshot["packing"]["parcels"]],
            [small.pk, small.pk],
        )

    def test_all_tariff_refusals_do_not_create_an_order_or_a_quote(self):
        self.alternative_plans()
        self.provider.calculate.side_effect = TariffUnavailable("Нет доступного тарифа для упаковки.")
        with self.assertRaises(DeliveryUnavailable):
            self.quote()
        self.assertEqual(self.provider.calculate.call_count, 2)
        self.assertFalse(Order.objects.exists())

    def test_service_outage_does_not_retry_all_packing_options(self):
        self.alternative_plans()
        self.provider.calculate.side_effect = DeliveryUnavailable("СДЭК не ответил. Повторите позже.")
        with self.assertRaisesMessage(DeliveryUnavailable, "не ответил"):
            self.quote()
        self.provider.calculate.assert_called_once()
        self.assertFalse(Order.objects.exists())

    def test_service_outage_after_a_success_does_not_hide_failed_comparison(self):
        self.alternative_plans()
        self.provider.calculate.side_effect = [
            self.price("600.00"),
            DeliveryUnavailable("СДЭК не ответил. Повторите позже."),
        ]
        with self.assertRaisesMessage(DeliveryUnavailable, "не ответил"):
            self.quote()
        self.assertEqual(self.provider.calculate.call_count, 2)
        self.assertFalse(Order.objects.exists())

    def test_comparison_budget_preserves_verified_success_and_marks_partial_search(self):
        self.alternative_plans()
        elapsed = [0]

        def calculate(*args, **kwargs):
            elapsed[0] = 21
            return self.price("600.00")

        self.provider.calculate.side_effect = calculate
        with patch("apps.orders.shipping.monotonic", side_effect=lambda: elapsed[0]):
            result = self.quote()
        self.provider.calculate.assert_called_once()
        self.assertEqual(result["shipping"]["price"], "600.00")
        comparison = result["shipping"]["packing_comparison"]
        self.assertEqual(comparison["attempted"], 1)
        self.assertEqual(comparison["successful"], 1)
        self.assertFalse(comparison["finished"])

    def test_exhausted_budget_after_refusal_is_not_reported_as_all_tariffs_unavailable(self):
        self.alternative_plans()
        elapsed = [0]

        def calculate(*args, **kwargs):
            elapsed[0] = 21
            raise TariffUnavailable("Нет тарифа для этой коробки.")

        self.provider.calculate.side_effect = calculate
        with (
            patch("apps.orders.shipping.monotonic", side_effect=lambda: elapsed[0]),
            self.assertRaises(DeliveryUnavailable) as error,
        ):
            self.quote()
        self.assertNotIsInstance(error.exception, TariffUnavailable)
        self.provider.calculate.assert_called_once()

    def test_many_single_parcel_variants_do_not_hide_compact_split(self):
        from .packing import packing_options

        _, small = self.alternative_plans()
        for extra in range(10):
            self.recipe(
                measured_weight_g=2000,
                outer_length_mm=810 + extra * 10,
                outer_width_mm=600,
                outer_height_mm=400,
            )
        plans = packing_options(self.cart, limit=8)
        self.assertLessEqual(len(plans), 8)
        self.assertIn(
            (small.pk, small.pk),
            {tuple(parcel["recipe_id"] for parcel in plan["parcels"]) for plan in plans},
        )

    def test_identical_carrier_packages_are_not_calculated_twice(self):
        self.recipe()
        self.recipe(instructions="Отдельная проверенная схема с такими же внешними параметрами.")
        self.quote()
        self.provider.calculate.assert_called_once()

    def test_unrelated_recipe_rename_does_not_expire_quote(self):
        self.recipe()
        unrelated = self.recipe(product=self.other_product())
        result = self.quote()
        unrelated.name = "Исправлено только название чужой схемы"
        unrelated.save(update_fields=["name", "updated_at"])
        self.assertEqual(self.verify(result), result["shipping"])

    def test_unrelated_box_edit_does_not_expire_quote(self):
        self.recipe()
        unrelated_box = PackingBox.objects.create(
            name="Неиспользуемая коробка",
            code="audit-unused",
            inner_length_mm=100,
            inner_width_mm=100,
            inner_height_mm=100,
            outer_length_mm=110,
            outer_width_mm=110,
            outer_height_mm=110,
            tare_weight_g=20,
            max_weight_g=1000,
        )
        result = self.quote()
        PackingBox.objects.filter(pk=unrelated_box.pk).update(tare_weight_g=30)
        self.assertEqual(self.verify(result), result["shipping"])

    def test_new_relevant_recipe_invalidates_previously_quoted_packing_choices(self):
        self.recipe()
        result = self.quote()
        self.recipe(quantity=1)
        with self.assertRaises(QuoteChanged):
            self.verify(result)

    def test_changed_selected_recipe_instructions_invalidate_quote(self):
        selected = self.recipe()
        result = self.quote()
        PackingRecipe.objects.filter(pk=selected.pk).update(instructions="Добавить защитную вставку.")
        with self.assertRaises(QuoteChanged):
            self.verify(result)

    def test_newly_eligible_recipe_invalidates_quote_after_composition_edit(self):
        self.recipe()
        unavailable = self.recipe(quantity=3)
        result = self.quote()
        unavailable.items.update(quantity=2)
        unavailable.confirm_measurements()
        with self.assertRaises(QuoteChanged):
            self.verify(result)

    def test_enabling_relevant_recipe_invalidates_quote(self):
        self.recipe()
        inactive = self.recipe(active=False)
        result = self.quote()
        PackingRecipe.objects.filter(pk=inactive.pk).update(active=True)
        with self.assertRaises(QuoteChanged):
            self.verify(result)
