"""Delivery prices must attest to the exact inputs used by the planner."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.catalog.models import Product
from . import packing
from .cdek import DeliveryUnavailable
from .models import PackingRecipe, PackingRecipeItem
from .packing import PreparedPacking
from .services import QuoteChanged
from .test_cdek import CDEK_SETTINGS
from . import test_packing_checkout as checkout_fixtures


@override_settings(**CDEK_SETTINGS)
class PackingSnapshotConcurrencyTests(TestCase):
    setUp = checkout_fixtures.MeasuredPackingCheckoutTests.setUp
    quote = checkout_fixtures.MeasuredPackingCheckoutTests.quote

    def alternative_recipe(self):
        recipe = PackingRecipe.objects.create(
            name="Временная альтернативная сборка",
            box=self.box,
            packing_weight_g=30,
            measured_weight_g=1121,
            outer_length_mm=187,
            outer_width_mm=108,
            outer_height_mm=128,
            instructions="Три защищённых флакона с дополнительной защитой.",
            active=False,
        )
        PackingRecipeItem.objects.create(recipe=recipe, product=self.product, quantity=3)
        recipe.confirm_measurements()
        return recipe

    def test_catalogue_returning_to_original_state_does_not_hide_different_planner_inputs(self):
        alternative = self.alternative_recipe()

        def changed_snapshot(*args, **kwargs):
            # The checkout signature describes A. The planner reads B. Then A
            # returns before any later DB check, making before/after hashes equal.
            PackingRecipe.objects.filter(pk=self.recipe.pk).update(active=False)
            PackingRecipe.objects.filter(pk=alternative.pk).update(active=True)
            prepared = PreparedPacking(*args, **kwargs)
            PackingRecipe.objects.filter(pk=self.recipe.pk).update(active=True)
            PackingRecipe.objects.filter(pk=alternative.pk).update(active=False)
            return prepared

        with (
            patch("apps.orders.shipping.PreparedPacking", side_effect=changed_snapshot),
            self.assertRaises(QuoteChanged),
        ):
            self.quote()
        self.provider.pickup.assert_not_called()
        self.provider.calculate.assert_not_called()

    def test_recipe_replaced_during_preparation_is_rejected_before_carrier_calls(self):
        alternative = self.alternative_recipe()

        def changed_snapshot(*args, **kwargs):
            PackingRecipe.objects.filter(pk=self.recipe.pk).update(active=False)
            PackingRecipe.objects.filter(pk=alternative.pk).update(active=True)
            return PreparedPacking(*args, **kwargs)

        def restored_after_calculation(*args, **kwargs):
            PackingRecipe.objects.filter(pk=self.recipe.pk).update(active=True)
            PackingRecipe.objects.filter(pk=alternative.pk).update(active=False)
            return {"price": "321.40", "period_min": 2, "period_max": 5}

        self.provider.calculate.side_effect = restored_after_calculation
        with (
            patch("apps.orders.shipping.PreparedPacking", side_effect=changed_snapshot),
            self.assertRaises(QuoteChanged),
        ):
            self.quote()
        self.provider.pickup.assert_not_called()
        self.provider.calculate.assert_not_called()

    def test_product_changed_between_cart_and_recipe_reads_cannot_form_mixed_snapshot(self):
        load_candidates = packing._load_candidates

        def changed_product(*args, **kwargs):
            Product.objects.filter(pk=self.product.pk).update(unit_length_mm=51)
            try:
                return load_candidates(*args, **kwargs)
            finally:
                Product.objects.filter(pk=self.product.pk).update(unit_length_mm=50)

        with (
            patch("apps.orders.packing._load_candidates", side_effect=changed_product),
            self.assertRaisesMessage(DeliveryUnavailable, "Параметры товаров изменились"),
        ):
            self.quote()
        self.provider.pickup.assert_not_called()
        self.provider.calculate.assert_not_called()
