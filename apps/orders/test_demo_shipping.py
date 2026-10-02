from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from .cdek import DeliveryUnavailable
from .management.commands.seed_demo_shipping import _require_local_sandbox
from .models import PackingBox, PackingRecipe, PackingRecipeItem
from .packing import packing_plan


@override_settings(DEBUG=True, CDEK_TEST_MODE=True, PAYMENT_STUB_ENABLED=True, ALFABANK_ENABLED=False)
class DemoShippingCommandTests(TestCase):
    def setUp(self):
        self.categories = {
            slug: Category.objects.create(slug=slug, name=slug)
            for slug in ("demo-hydrolats", "demo-oils", "demo-water", "demo-sets")
        }
        self.oil = self.product("DEMO-001", "demo-oils", "199.00")
        self.hydrolat = self.product("DEMO-009", "demo-hydrolats", "299.00")
        self.second_hydrolat = self.product("DEMO-010", "demo-hydrolats", "399.00")
        self.ozone = self.product("DEMO-013", "demo-water", "5000.00")
        # Water systems stay untouched even if a second category was selected.
        self.ozone.categories.add(self.categories["demo-oils"])
        self.old_oil_set = self.product("DEMO-014", "demo-sets", "3490.00")
        self.real_oil = self.product("REAL-OIL", "demo-oils", "999.00")
        self.cart = Cart.objects.create(session_key="demo-shipping-command")

    def product(self, sku, category, price):
        product = Product.objects.create(
            sku=sku,
            slug=sku.lower(),
            name=sku,
            price=price,
            package_weight_g=850,
            package_length_cm=25,
            package_width_cm=20,
            package_height_cm=10,
        )
        product.categories.add(self.categories[category])
        return product

    def seed(self):
        output = StringIO()
        call_command("seed_demo_shipping", stdout=output)
        return output.getvalue()

    def plan(self, *pairs, **kwargs):
        self.cart.items.all().delete()
        CartItem.objects.bulk_create(
            [CartItem(cart=self.cart, product=product, quantity=quantity) for product, quantity in pairs]
        )
        return packing_plan(self.cart, **kwargs)

    def test_exact_user_dimensions_and_separate_hydrolat_gift_set(self):
        self.seed()
        gift = Product.objects.get(sku="DEMO-HYDROLAT-SET")
        expected = [
            (self.hydrolat, (150, 60, 60, 180)),
            (self.second_hydrolat, (150, 60, 60, 180)),
            (self.oil, (70, 40, 40, 100)),
            (gift, (500, 240, 60, 180)),
        ]
        for product, profile in expected:
            with self.subTest(sku=product.sku):
                product.refresh_from_db()
                self.assertEqual(
                    (
                        product.unit_weight_g,
                        product.unit_length_mm,
                        product.unit_width_mm,
                        product.unit_height_mm,
                    ),
                    profile,
                )
                self.assertEqual(product.shipping_mode, "combined")
                self.assertEqual(product.package_measurement_signature, "")
                self.assertIsNone(product.package_measured_at)
                self.assertFalse(product.package_measurements_valid)
        self.assertEqual(gift.price, Decimal("1000.00"))
        self.assertTrue(gift.purchasable)
        self.assertEqual(gift.status, "published")
        self.assertEqual(list(gift.categories.values_list("slug", flat=True)), ["demo-sets"])
        self.assertNotEqual(gift.pk, self.old_oil_set.pk)

    def test_ozonation_existing_oil_sets_and_non_demo_products_are_unchanged(self):
        untouched = [self.ozone.pk, self.old_oil_set.pk, self.real_oil.pk]
        before = list(Product.objects.filter(pk__in=untouched).order_by("pk").values())
        categories_before = list(
            Product.categories.through.objects.filter(product_id__in=untouched).order_by("pk").values()
        )
        self.seed()
        self.assertEqual(before, list(Product.objects.filter(pk__in=untouched).order_by("pk").values()))
        self.assertEqual(
            categories_before,
            list(Product.categories.through.objects.filter(product_id__in=untouched).order_by("pk").values()),
        )
        self.assertFalse(PackingRecipeItem.objects.filter(product_id__in=untouched).exists())

    def test_all_created_recipes_are_explicit_fiction_with_no_measurement_stamps(self):
        self.seed()
        self.assertEqual(PackingBox.objects.count(), 3)
        self.assertGreater(PackingRecipe.objects.count(), 10)
        for recipe in PackingRecipe.objects.select_related("box"):
            with self.subTest(recipe=recipe.name):
                self.assertTrue(recipe.test_only)
                self.assertTrue(recipe.active)
                self.assertFalse(recipe.measurements_valid)
                self.assertEqual(recipe.measurement_signature, "")
                self.assertIsNone(recipe.measured_at)
                recipe.validate_measurements()
                rows = list(recipe.items.select_related("product"))
                self.assertEqual(
                    recipe.measured_weight_g,
                    sum(row.quantity * row.product.unit_weight_g for row in rows)
                    + recipe.box.tare_weight_g
                    + recipe.packing_weight_g,
                )
                self.assertLessEqual(
                    sum(row.quantity * row.product.unit_length_mm for row in rows),
                    recipe.box.inner_length_mm,
                )
                self.assertIn("УЧЕБНАЯ СХЕМА", recipe.instructions)

    def test_single_mixed_and_count_cases_include_one_shared_tare_per_parcel(self):
        self.seed()
        gift = Product.objects.get(sku="DEMO-HYDROLAT-SET")
        cases = [
            ([(self.hydrolat, 1)], [{"weight": 200, "length": 11, "width": 11, "height": 20}]),
            ([(self.hydrolat, 2)], [{"weight": 410, "length": 29, "width": 19, "height": 20}]),
            ([(self.hydrolat, 3)], [{"weight": 560, "length": 29, "width": 19, "height": 20}]),
            ([(self.hydrolat, 4)], [{"weight": 710, "length": 29, "width": 19, "height": 20}]),
            ([(self.hydrolat, 6)], [{"weight": 1090, "length": 39, "width": 29, "height": 20}]),
            ([(self.oil, 1)], [{"weight": 120, "length": 11, "width": 11, "height": 20}]),
            ([(self.oil, 2)], [{"weight": 190, "length": 11, "width": 11, "height": 20}]),
            (
                [(self.hydrolat, 1), (self.oil, 1)],
                [{"weight": 270, "length": 11, "width": 11, "height": 20}],
            ),
            (
                [(self.hydrolat, 1), (self.second_hydrolat, 1)],
                [{"weight": 410, "length": 29, "width": 19, "height": 20}],
            ),
            ([(gift, 1)], [{"weight": 610, "length": 29, "width": 19, "height": 20}]),
            (
                [(gift, 1), (self.hydrolat, 1)],
                [{"weight": 840, "length": 39, "width": 29, "height": 20}],
            ),
            (
                [(gift, 1), (self.oil, 1)],
                [{"weight": 680, "length": 29, "width": 19, "height": 20}],
            ),
            ([(self.hydrolat, 8)], [{"weight": 710, "length": 29, "width": 19, "height": 20}] * 2),
            ([(gift, 2)], [{"weight": 610, "length": 29, "width": 19, "height": 20}] * 2),
        ]
        for pairs, packages in cases:
            with self.subTest(composition=[(p.sku, count) for p, count in pairs]):
                plan = self.plan(*pairs)
                self.assertEqual(plan["packages"], packages)
                self.assertFalse(plan["measurements_confirmed"])
                actual = {}
                for parcel in plan["parcels"]:
                    self.assertTrue(parcel["test_only"])
                    self.assertFalse(parcel["measurements_confirmed"])
                    for item in parcel["contents"]:
                        actual[item["product_id"]] = actual.get(item["product_id"], 0) + item["quantity"]
                self.assertEqual(actual, {product.pk: count for product, count in pairs})
                # The caller cannot force seeded fiction into a live environment.
                with self.settings(CDEK_TEST_MODE=False), self.assertRaises(DeliveryUnavailable):
                    packing_plan(self.cart, test_mode=True)

    def test_repeated_seeding_preserves_ids_counts_and_catalog_prices(self):
        self.seed()
        Product.objects.filter(pk=self.hydrolat.pk).update(price="123.45")
        Product.objects.filter(sku="DEMO-HYDROLAT-SET").update(price="1234.56")
        prices = dict(Product.objects.values_list("sku", "price"))
        identities = {
            model: list(model.objects.order_by("pk").values_list("pk", flat=True))
            for model in (Product, PackingBox, PackingRecipe, PackingRecipeItem)
        }
        first_plan = self.plan((self.hydrolat, 2), (self.oil, 1))
        self.seed()
        self.assertEqual(prices, dict(Product.objects.values_list("sku", "price")))
        for model, pks in identities.items():
            self.assertEqual(pks, list(model.objects.order_by("pk").values_list("pk", flat=True)))
        self.assertEqual(first_plan, packing_plan(self.cart))

    def test_every_forbidden_environment_refuses_without_data_changes(self):
        before = list(Product.objects.order_by("pk").values())
        for forbidden in (
            {"DEBUG": False},
            {"CDEK_TEST_MODE": False},
            {"PAYMENT_STUB_ENABLED": False},
            {"ALFABANK_ENABLED": True},
        ):
            with self.subTest(forbidden=forbidden), self.settings(**forbidden):
                with self.assertRaisesMessage(CommandError, "только в локальной SQLite"):
                    self.seed()
            self.assertEqual(before, list(Product.objects.order_by("pk").values()))
            self.assertFalse(PackingBox.objects.exists())
            self.assertFalse(PackingRecipe.objects.exists())

    def test_nonlocal_or_non_sqlite_database_configuration_is_refused(self):
        original = settings.DATABASES["default"].copy()
        configs = (
            {**original, "ENGINE": "django.db.backends.postgresql"},
            {**original, "NAME": str(Path(settings.BASE_DIR).parent / "outside-workspace.sqlite3")},
        )
        for config in configs:
            with self.subTest(config=config["ENGINE"]):
                with patch.object(settings, "DATABASES", {"default": config}):
                    with self.assertRaisesMessage(CommandError, "только в локальной SQLite"):
                        _require_local_sandbox()

    def test_refuses_confirmed_individual_product_and_rolls_back_earlier_changes(self):
        # Oil sorts first and would be changed before this protected hydrolat.
        self.hydrolat.confirm_package_measurements()
        before = list(Product.objects.order_by("pk").values())
        with self.assertRaisesMessage(CommandError, "уже подтверждены реальные замеры"):
            self.seed()
        self.assertEqual(before, list(Product.objects.order_by("pk").values()))
        self.assertFalse(Product.objects.filter(sku="DEMO-HYDROLAT-SET").exists())
        self.assertFalse(PackingBox.objects.exists())
        self.assertFalse(PackingRecipe.objects.exists())
        self.hydrolat.refresh_from_db()
        self.assertTrue(self.hydrolat.package_measurements_valid)

    def test_refuses_product_used_by_confirmed_real_combined_recipe(self):
        # Use a different box and recipe name from the seed command so only
        # protection of the shared product measurements can catch the conflict.
        Product.objects.filter(pk=self.hydrolat.pk).update(
            shipping_mode="combined",
            unit_weight_g=155,
            unit_length_mm=61,
            unit_width_mm=61,
            unit_height_mm=181,
        )
        box = PackingBox.objects.create(
            name="Реальная коробка",
            code="real-confirmed-box",
            inner_length_mm=100,
            inner_width_mm=100,
            inner_height_mm=190,
            outer_length_mm=110,
            outer_width_mm=110,
            outer_height_mm=200,
            tare_weight_g=50,
            max_weight_g=1000,
        )
        recipe = PackingRecipe.objects.create(
            name="Подтверждённая сборка гидролата",
            box=box,
            measured_weight_g=205,
            outer_length_mm=110,
            outer_width_mm=110,
            outer_height_mm=200,
            instructions="Поставить один защищённый флакон вертикально.",
        )
        PackingRecipeItem.objects.create(recipe=recipe, product=self.hydrolat, quantity=1)
        recipe.confirm_measurements()
        self.assertTrue(recipe.measurements_valid)
        self.assertFalse(recipe.active)
        self.hydrolat.refresh_from_db()
        self.assertEqual(self.hydrolat.package_measurement_signature, "")

        for stale in (False, True):
            with self.subTest(stale=stale):
                if stale:
                    Product.objects.filter(pk=self.hydrolat.pk).update(unit_weight_g=156)
                before = {
                    model: list(model.objects.order_by("pk").values())
                    for model in (Product, PackingBox, PackingRecipe, PackingRecipeItem)
                }
                with self.assertRaisesMessage(CommandError, "уже подтверждены реальные замеры"):
                    self.seed()
                for model, records in before.items():
                    self.assertEqual(records, list(model.objects.order_by("pk").values()))
                self.assertFalse(Product.objects.filter(sku="DEMO-HYDROLAT-SET").exists())
