import json
from itertools import combinations_with_replacement
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Product
from .cdek import DeliveryUnavailable
from .models import PackingBox, PackingRecipe
from .packing import packing_configuration, packing_plan


@override_settings(CDEK_TEST_MODE=False)
class PackingPlanTests(TestCase):
    def setUp(self):
        self.cart = Cart.objects.create(session_key="packing-owner")
        self.box = PackingBox.objects.create(
            code="measured-box",
            name="Измеренная коробка",
            inner_length_mm=300,
            inner_width_mm=200,
            inner_height_mm=150,
            outer_length_mm=310,
            outer_width_mm=210,
            outer_height_mm=160,
            tare_weight_g=100,
            max_weight_g=20000,
            active=True,
        )
        self.a = self.product("A")
        self.b = self.product("B", unit_weight_g=150)

    def product(self, sku, **overrides):
        return Product.objects.create(
            **{
                "name": f"Товар {sku}",
                "sku": sku,
                "slug": sku.lower(),
                "price": "100.00",
                "shipping_mode": "combined",
                "unit_weight_g": 100,
                "unit_length_mm": 20,
                "unit_width_mm": 20,
                "unit_height_mm": 30,
                **overrides,
            }
        )

    def cart_items(self, *pairs):
        self.cart.items.all().delete()
        for product, quantity in pairs:
            CartItem.objects.create(cart=self.cart, product=product, quantity=quantity)

    def recipe(self, *pairs, confirmed=True, **overrides):
        recipe = PackingRecipe.objects.create(
            **{
                "name": f"Схема {PackingRecipe.objects.count() + 1}",
                "box": self.box,
                "packing_weight_g": 20,
                "measured_weight_g": sum(product.unit_weight_g * quantity for product, quantity in pairs)
                + 120,
                "outer_length_mm": 311,
                "outer_width_mm": 211,
                "outer_height_mm": 161,
                "instructions": "Собрать по проверенной схеме, разделить товары защитными вставками.",
                "active": True,
                **overrides,
            }
        )
        for product, quantity in pairs:
            recipe.items.create(product=product, quantity=quantity)
        if confirmed:
            recipe.confirm_measurements()
        return recipe

    def assert_contents(self, plan, expected):
        actual = {}
        for parcel in plan["parcels"]:
            for item in parcel["contents"]:
                actual[item["product_id"]] = actual.get(item["product_id"], 0) + item["quantity"]
        self.assertEqual(actual, {product.pk: quantity for product, quantity in expected})

    def test_mixed_cart_uses_measured_gross_and_outer_dimensions_rounded_up(self):
        self.cart_items((self.a, 3), (self.b, 2))
        recipe = self.recipe((self.a, 3), (self.b, 2), measured_weight_g=750)
        plan = packing_plan(self.cart)
        self.assertEqual(plan["packages"], [{"weight": 750, "length": 32, "width": 22, "height": 17}])
        self.assertEqual(plan["parcels"][0]["recipe_id"], recipe.pk)
        self.assertEqual(plan["parcels"][0]["dimensions_mm"], {"length": 311, "width": 211, "height": 161})
        self.assertEqual(plan["parcels"][0]["box_code"], self.box.code)
        self.assertEqual(plan["parcels"][0]["instructions"], recipe.instructions)
        self.assert_contents(plan, [(self.a, 3), (self.b, 2)])
        self.assertTrue(plan["measurements_confirmed"])
        self.assertEqual(json.loads(json.dumps(plan)), plan)

    def test_exact_recipe_can_repeat_and_split_into_multiple_parcels(self):
        self.cart_items((self.a, 4), (self.b, 2))
        recipe = self.recipe((self.a, 2), (self.b, 1), measured_weight_g=500)
        plan = packing_plan(self.cart)
        self.assertEqual([row["recipe_id"] for row in plan["parcels"]], [recipe.pk, recipe.pk])
        self.assertEqual([row["weight"] for row in plan["packages"]], [500, 500])
        self.assert_contents(plan, [(self.a, 4), (self.b, 2)])
        self.assertIsNot(plan["parcels"][0], plan["parcels"][1])
        self.assertIsNot(plan["parcels"][0]["contents"], plan["parcels"][1]["contents"])

    def test_complete_search_avoids_greedy_dead_end(self):
        self.cart_items((self.a, 6))
        self.recipe((self.a, 4))
        usable = self.recipe((self.a, 3))
        plan = packing_plan(self.cart)
        self.assertEqual([row["recipe_id"] for row in plan["parcels"]], [usable.pk, usable.pk])
        self.assert_contents(plan, [(self.a, 6)])

    def test_complete_search_handles_mixed_sku_dead_end(self):
        self.cart_items((self.a, 4), (self.b, 4))
        self.recipe((self.a, 3), (self.b, 3))
        a_box = self.recipe((self.a, 4))
        b_box = self.recipe((self.b, 4))
        plan = packing_plan(self.cart)
        self.assertEqual([row["recipe_id"] for row in plan["parcels"]], [a_box.pk, b_box.pk])
        self.assert_contents(plan, [(self.a, 4), (self.b, 4)])

    def test_fewer_parcels_take_priority_over_smaller_volume(self):
        self.cart_items((self.a, 4))
        self.recipe((self.a, 2))
        one = self.recipe((self.a, 4), outer_length_mm=700)
        self.assertEqual([row["recipe_id"] for row in packing_plan(self.cart)["parcels"]], [one.pk])

    def test_equal_parcel_count_prefers_total_volume_before_total_weight(self):
        self.cart_items((self.a, 6))
        self.recipe((self.a, 4), outer_length_mm=600)
        self.recipe((self.a, 2), outer_length_mm=600)
        smaller = self.recipe((self.a, 3), measured_weight_g=600)
        plan = packing_plan(self.cart)
        self.assertEqual([row["recipe_id"] for row in plan["parcels"]], [smaller.pk, smaller.pk])

    def test_identical_composition_prefers_volume_then_weight_then_stable_id(self):
        self.cart_items((self.a, 2))
        self.recipe((self.a, 2), outer_length_mm=500, measured_weight_g=320)
        self.recipe((self.a, 2), measured_weight_g=400)
        best = self.recipe((self.a, 2), measured_weight_g=350)
        self.recipe((self.a, 2), measured_weight_g=350)
        self.assertEqual(packing_plan(self.cart)["parcels"][0]["recipe_id"], best.pk)
        self.assertEqual(packing_plan(self.cart), packing_plan(self.cart))

    def test_optimizer_matches_exhaustive_enumeration_across_small_mixed_carts(self):
        arrangements = [
            (1, 0, self.recipe((self.a, 1))),
            (0, 1, self.recipe((self.b, 1), outer_length_mm=400)),
            (2, 0, self.recipe((self.a, 2), outer_length_mm=350)),
            (1, 1, self.recipe((self.a, 1), (self.b, 1), outer_length_mm=450)),
            (1, 2, self.recipe((self.a, 1), (self.b, 2), outer_length_mm=500)),
        ]
        for a_count in range(1, 5):
            for b_count in range(1, 5):
                with self.subTest(a=a_count, b=b_count):
                    self.cart_items((self.a, a_count), (self.b, b_count))
                    oracle = None
                    # Independent, deliberately simple enumeration of all multisets.
                    for number in range(1, a_count + b_count + 1):
                        for choices in combinations_with_replacement(arrangements, number):
                            if (
                                sum(row[0] for row in choices) != a_count
                                or sum(row[1] for row in choices) != b_count
                            ):
                                continue
                            score = (
                                number,
                                sum(
                                    ((row[2].outer_length_mm + 9) // 10)
                                    * ((row[2].outer_width_mm + 9) // 10)
                                    * ((row[2].outer_height_mm + 9) // 10)
                                    for row in choices
                                ),
                                sum(row[2].measured_weight_g for row in choices),
                                tuple(sorted(row[2].pk for row in choices)),
                            )
                            oracle = min(oracle, score) if oracle is not None else score
                        if oracle is not None:
                            break
                    plan = packing_plan(self.cart)
                    self.assertEqual(tuple(row["recipe_id"] for row in plan["parcels"]), oracle[3])
                    self.assert_contents(plan, [(self.a, a_count), (self.b, b_count)])

    def test_cannot_substitute_a_recipe_for_more_or_different_products(self):
        self.cart_items((self.a, 1))
        self.recipe((self.a, 2))
        self.recipe((self.a, 1), (self.b, 1))
        with self.assertRaisesMessage(DeliveryUnavailable, "состава и количества"):
            packing_plan(self.cart)

    def test_uncovered_combined_quantity_never_uses_individual_fallback(self):
        self.cart_items((self.a, 3))
        self.recipe((self.a, 2))
        self.a.package_weight_g = 300
        self.a.package_length_cm = 20
        self.a.package_width_cm = 10
        self.a.package_height_cm = 10
        self.a.save()
        for test_mode in (False, True):
            with self.subTest(test_mode=test_mode), self.assertRaises(DeliveryUnavailable):
                packing_plan(self.cart, test_mode=test_mode)

    def test_inactive_recipe_and_inactive_box_are_not_used(self):
        self.cart_items((self.a, 2))
        recipe = self.recipe((self.a, 2))
        PackingRecipe.objects.filter(pk=recipe.pk).update(active=False)
        with self.assertRaises(DeliveryUnavailable):
            packing_plan(self.cart)
        PackingRecipe.objects.filter(pk=recipe.pk).update(active=True)
        PackingBox.objects.filter(pk=self.box.pk).update(active=False)
        with self.assertRaises(DeliveryUnavailable):
            packing_plan(self.cart)

    def test_unconfirmed_recipe_is_refused_even_in_test_environment(self):
        self.cart_items((self.a, 2))
        self.recipe((self.a, 2), confirmed=False)
        with self.assertRaises(DeliveryUnavailable):
            packing_plan(self.cart, test_mode=True)

    @override_settings(CDEK_TEST_MODE=True)
    def test_explicit_fictional_recipe_works_without_fabricated_measurement_stamp(self):
        self.cart_items((self.a, 4), (self.b, 2))
        recipe = self.recipe((self.a, 2), (self.b, 1), confirmed=False, test_only=True)
        plan = packing_plan(self.cart)
        self.assertEqual([p["recipe_id"] for p in plan["parcels"]], [recipe.pk, recipe.pk])
        self.assertEqual(plan["packages"], [{"weight": 470, "length": 32, "width": 22, "height": 17}] * 2)
        self.assertFalse(plan["measurements_confirmed"])
        self.assertTrue(all(p["test_only"] and not p["measurements_confirmed"] for p in plan["parcels"]))
        self.assert_contents(plan, [(self.a, 4), (self.b, 2)])
        recipe.refresh_from_db()
        self.assertFalse(recipe.measurements_valid)
        self.assertEqual(recipe.measurement_signature, "")
        self.assertIsNone(recipe.measured_at)
        with self.assertRaises(DeliveryUnavailable):
            packing_plan(self.cart, test_mode=False)

    def test_fictional_recipe_cannot_enter_live_mode_even_with_caller_override(self):
        self.cart_items((self.a, 2))
        self.recipe((self.a, 2), confirmed=False, test_only=True)
        for test_mode in (None, False, True):
            with self.subTest(test_mode=test_mode), self.assertRaises(DeliveryUnavailable):
                packing_plan(self.cart, test_mode=test_mode)

    @override_settings(CDEK_TEST_MODE=True)
    def test_fictional_recipe_still_requires_valid_structure_and_gross_weight(self):
        self.cart_items((self.a, 2))
        recipe = self.recipe((self.a, 2), confirmed=False, test_only=True)
        changes = (
            {"measured_weight_g": 310},
            {"outer_length_mm": 1},
            {"instructions": ""},
            {"active": False},
        )
        for invalid in changes:
            with self.subTest(invalid=invalid):
                PackingRecipe.objects.filter(pk=recipe.pk).update(**invalid)
                with self.assertRaises(DeliveryUnavailable):
                    packing_plan(self.cart)
                recipe.save()
        Product.objects.filter(pk=self.a.pk).update(unit_weight_g=500)
        with self.assertRaises(DeliveryUnavailable):
            packing_plan(self.cart)

    def test_fictional_compact_recipe_is_used_only_in_sandbox(self):
        self.cart_items((self.a, 2))
        real = self.recipe((self.a, 1))
        fictional = self.recipe((self.a, 2), confirmed=False, test_only=True)
        plan = packing_plan(self.cart, test_mode=True)
        self.assertEqual([p["recipe_id"] for p in plan["parcels"]], [real.pk, real.pk])
        self.assertTrue(plan["measurements_confirmed"])
        with self.settings(CDEK_TEST_MODE=True):
            plan = packing_plan(self.cart)
        self.assertEqual([p["recipe_id"] for p in plan["parcels"]], [fictional.pk])
        self.assertFalse(plan["measurements_confirmed"])

    @override_settings(CDEK_TEST_MODE=True)
    def test_mixed_real_and_fictional_plan_remains_unconfirmed(self):
        self.cart_items((self.a, 1), (self.b, 1))
        self.recipe((self.a, 1))
        self.recipe((self.b, 1), confirmed=False, test_only=True)
        plan = packing_plan(self.cart)
        self.assertEqual([p["measurements_confirmed"] for p in plan["parcels"]], [True, False])
        self.assertFalse(plan["measurements_confirmed"])
        self.assert_contents(plan, [(self.a, 1), (self.b, 1)])

    def test_live_candidate_limit_does_not_count_test_only_recipes(self):
        self.cart_items((self.a, 2))
        self.recipe((self.a, 2), confirmed=False, test_only=True)
        real = self.recipe((self.a, 2))
        with patch("apps.orders.packing.MAX_CANDIDATE_RECIPES", 1):
            self.assertEqual(packing_plan(self.cart)["parcels"][0]["recipe_id"], real.pk)

    def test_changed_product_measurements_stale_recipe(self):
        self.cart_items((self.a, 2))
        self.recipe((self.a, 2))
        Product.objects.filter(pk=self.a.pk).update(unit_length_mm=21)
        with self.assertRaises(DeliveryUnavailable):
            packing_plan(self.cart)

    def test_changed_box_measurements_stale_recipe(self):
        self.cart_items((self.a, 2))
        self.recipe((self.a, 2))
        PackingBox.objects.filter(pk=self.box.pk).update(tare_weight_g=101)
        with self.assertRaises(DeliveryUnavailable):
            packing_plan(self.cart)

    def test_changed_recipe_composition_stales_approval(self):
        self.cart_items((self.a, 1))
        recipe = self.recipe((self.a, 2))
        recipe.items.update(quantity=1)
        with self.assertRaises(DeliveryUnavailable):
            packing_plan(self.cart)

    def test_unknown_mode_fails_instead_of_guessing(self):
        self.cart_items((self.a, 1))
        Product.objects.filter(pk=self.a.pk).update(shipping_mode="unknown")
        with self.assertRaisesMessage(DeliveryUnavailable, "способ упаковки"):
            packing_plan(self.cart)

    def test_individual_shipping_requires_current_confirmation_in_live_environment(self):
        single = self.product(
            "individual",
            shipping_mode="individual",
            package_weight_g=350,
            package_length_cm=20,
            package_width_cm=10,
            package_height_cm=8,
        )
        self.cart_items((single, 2))
        with self.assertRaisesMessage(DeliveryUnavailable, "не подтверждены"):
            packing_plan(self.cart)
        single.confirm_package_measurements()
        plan = packing_plan(self.cart)
        self.assertEqual(plan["packages"], [{"weight": 350, "length": 20, "width": 10, "height": 8}] * 2)
        self.assertTrue(plan["measurements_confirmed"])
        Product.objects.filter(pk=single.pk).update(package_weight_g=351)
        with self.assertRaises(DeliveryUnavailable):
            packing_plan(self.cart)

    @override_settings(CDEK_TEST_MODE=True)
    def test_legacy_individual_test_data_is_explicitly_unconfirmed(self):
        single = self.product(
            "individual",
            shipping_mode="individual",
            package_weight_g=350,
            package_length_cm=20,
            package_width_cm=10,
            package_height_cm=8,
        )
        self.cart_items((single, 1))
        plan = packing_plan(self.cart, test_mode=True)
        self.assertFalse(plan["measurements_confirmed"])
        self.assertFalse(plan["parcels"][0]["measurements_confirmed"])

    def test_individual_without_dimensions_is_refused_in_test_environment(self):
        single = self.product("individual", shipping_mode="individual")
        self.cart_items((single, 1))
        with self.assertRaisesMessage(DeliveryUnavailable, "упаковка"):
            packing_plan(self.cart, test_mode=True)

    def test_mixed_modes_keep_individual_goods_out_of_shared_parcel(self):
        single = self.product(
            "individual",
            shipping_mode="individual",
            package_weight_g=350,
            package_length_cm=20,
            package_width_cm=10,
            package_height_cm=8,
        )
        single.confirm_package_measurements()
        recipe = self.recipe((self.a, 2))
        self.cart_items((self.a, 2), (single, 1))
        plan = packing_plan(self.cart)
        self.assertEqual([parcel["kind"] for parcel in plan["parcels"]], ["individual", "recipe"])
        self.assertEqual(plan["parcels"][1]["recipe_id"], recipe.pk)
        self.assert_contents(plan, [(self.a, 2), (single, 1)])

    def test_empty_cart_and_cart_unit_limit_are_refused(self):
        with self.assertRaisesMessage(DeliveryUnavailable, "Добавьте товары"):
            packing_plan(self.cart)
        self.cart_items((self.a, 51), (self.b, 50))
        with self.assertRaisesMessage(DeliveryUnavailable, "такого количества"):
            packing_plan(self.cart)

    def test_one_hundred_units_can_be_exactly_covered(self):
        self.cart_items((self.a, 100))
        self.recipe((self.a, 1))
        plan = packing_plan(self.cart)
        self.assertEqual(len(plan["parcels"]), 100)
        self.assert_contents(plan, [(self.a, 100)])

    def test_search_budget_refuses_incomplete_optimum_instead_of_returning_guess(self):
        self.cart_items((self.a, 6))
        self.recipe((self.a, 2))
        self.recipe((self.a, 3))
        with patch("apps.orders.packing.MAX_SEARCH_STATES", 2):
            with self.assertRaisesMessage(DeliveryUnavailable, "подбор упаковки сотрудником"):
                packing_plan(self.cart)

    def test_transition_budget_is_also_bounded(self):
        self.cart_items((self.a, 6))
        self.recipe((self.a, 2))
        self.recipe((self.a, 3))
        with patch("apps.orders.packing.MAX_SEARCH_ATTEMPTS", 1), self.assertRaises(DeliveryUnavailable):
            packing_plan(self.cart)

    def test_recipe_catalogue_limit_does_not_silently_ignore_candidates(self):
        self.cart_items((self.a, 2))
        self.recipe((self.a, 1))
        self.recipe((self.a, 2))
        with patch("apps.orders.packing.MAX_CANDIDATE_RECIPES", 1), self.assertRaises(DeliveryUnavailable):
            packing_plan(self.cart)

    def test_configuration_serializes_deterministically_and_tracks_related_changes(self):
        recipe = self.recipe((self.a, 2))
        snapshot = packing_configuration()
        self.assertEqual(json.loads(json.dumps(snapshot)), snapshot)
        self.assertEqual(snapshot, packing_configuration())
        PackingBox.objects.filter(pk=self.box.pk).update(tare_weight_g=101)
        updated = packing_configuration()
        self.assertNotEqual(snapshot, updated)
        Product.objects.filter(pk=self.a.pk).update(unit_width_mm=21)
        next_update = packing_configuration()
        self.assertNotEqual(updated, next_update)
        recipe.items.update(quantity=1)
        changed_composition = packing_configuration()
        self.assertNotEqual(next_update, changed_composition)
        PackingRecipe.objects.filter(pk=recipe.pk).update(active=False)
        self.assertNotEqual(changed_composition, packing_configuration())

    def test_configuration_includes_drafts_and_confirmation_metadata(self):
        recipe = self.recipe((self.a, 2), active=False, confirmed=False)
        snapshot = packing_configuration()
        self.assertEqual(len(snapshot["recipes"]), 1)
        recipe.confirm_measurements()
        self.assertNotEqual(snapshot, packing_configuration())

    def test_configuration_fingerprint_includes_test_only_flag(self):
        recipe = self.recipe((self.a, 2), confirmed=False)
        snapshot = packing_configuration()
        PackingRecipe.objects.filter(pk=recipe.pk).update(test_only=True)
        self.assertNotEqual(snapshot, packing_configuration())

    def test_pickup_maximum_can_select_more_feasible_parcels(self):
        self.cart_items((self.a, 2))
        compact = self.recipe((self.a, 2), measured_weight_g=900)
        split = self.recipe((self.a, 1), measured_weight_g=450)
        self.assertEqual(packing_plan(self.cart)["parcels"][0]["recipe_id"], compact.pk)
        plan = packing_plan(self.cart, pickup={"weight_max_g": "500"})
        self.assertEqual([row["recipe_id"] for row in plan["parcels"]], [split.pk, split.pk])
        self.assertEqual([row["weight"] for row in plan["packages"]], [450, 450])
        self.assert_contents(plan, [(self.a, 2)])

    def test_pickup_filter_precedes_same_composition_dominance(self):
        self.cart_items((self.a, 2))
        self.recipe((self.a, 2), measured_weight_g=600)
        feasible = self.recipe((self.a, 2), measured_weight_g=450, outer_length_mm=500)
        plan = packing_plan(self.cart, pickup={"weight_max_g": "500"})
        self.assertEqual([row["recipe_id"] for row in plan["parcels"]], [feasible.pk])

    def test_pickup_minimum_can_select_heavier_measured_alternative(self):
        self.cart_items((self.a, 1))
        self.recipe((self.a, 1), measured_weight_g=220)
        feasible = self.recipe((self.a, 1), measured_weight_g=350, outer_length_mm=500)
        plan = packing_plan(self.cart, pickup={"weight_min_g": "300", "weight_max_g": "0"})
        self.assertEqual([row["recipe_id"] for row in plan["parcels"]], [feasible.pk])

    def test_pickup_bounds_are_inclusive_and_per_individual_parcel(self):
        single = self.product(
            "individual",
            shipping_mode="individual",
            package_weight_g=450,
            package_length_cm=20,
            package_width_cm=10,
            package_height_cm=8,
        )
        single.confirm_package_measurements()
        self.cart_items((single, 2))
        plan = packing_plan(self.cart, pickup={"weight_min_g": "450", "weight_max_g": "450"})
        self.assertEqual(len(plan["packages"]), 2)
        self.assertEqual(sum(row["weight"] for row in plan["packages"]), 900)
        self.assertTrue(plan["measurements_confirmed"])

    def test_individual_parcel_cannot_bypass_pickup_weight_limits(self):
        single = self.product(
            "individual",
            shipping_mode="individual",
            package_weight_g=450,
            package_length_cm=20,
            package_width_cm=10,
            package_height_cm=8,
        )
        single.confirm_package_measurements()
        self.cart_items((single, 1))
        for pickup in ({"weight_max_g": "449.9"}, {"weight_min_g": "450.1"}):
            with self.subTest(pickup=pickup), self.assertRaisesMessage(DeliveryUnavailable, "Этот пункт"):
                packing_plan(self.cart, pickup=pickup)

    def test_unavailable_pickup_explains_weight_restrictions_not_missing_measurements(self):
        self.cart_items((self.a, 2))
        self.recipe((self.a, 2), measured_weight_g=900)
        with self.assertRaisesMessage(DeliveryUnavailable, "Этот пункт не принимает доступные варианты"):
            packing_plan(self.cart, pickup={"weight_max_g": "500"})

    def test_missing_generic_packing_is_distinct_from_pickup_restrictions(self):
        self.cart_items((self.a, 3))
        self.recipe((self.a, 2), measured_weight_g=900)
        with self.assertRaisesMessage(DeliveryUnavailable, "ещё не проверена общая упаковка"):
            packing_plan(self.cart, pickup={"weight_max_g": "500"})

    def test_invalid_pickup_bounds_fail_before_selecting_parcels(self):
        self.cart_items((self.a, 2))
        self.recipe((self.a, 2))
        for pickup in (
            {"weight_max_g": "NaN"},
            {"weight_min_g": "-1"},
            {"weight_min_g": "500", "weight_max_g": "400"},
        ):
            with (
                self.subTest(pickup=pickup),
                self.assertRaisesMessage(DeliveryUnavailable, "ограничения пункта"),
            ):
                packing_plan(self.cart, pickup=pickup)

    def test_missing_or_zero_pickup_bounds_keep_generic_plan(self):
        self.cart_items((self.a, 2))
        self.recipe((self.a, 2))
        self.assertEqual(packing_plan(self.cart), packing_plan(self.cart, pickup={}))
        self.assertEqual(
            packing_plan(self.cart),
            packing_plan(self.cart, pickup={"weight_min_g": "0", "weight_max_g": "0"}),
        )
