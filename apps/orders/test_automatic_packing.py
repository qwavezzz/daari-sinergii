import copy
import json
from io import StringIO
from collections import Counter
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Product
from apps.core.management.commands.check_store_readiness import packing_coverage
from .auto_geometry import Budget, SearchLimit, fit_all
from .automatic_packing import AutomaticPacking
from .cdek import DeliveryUnavailable
from .models import PackingBox
from .packing import packing_configuration, packing_options, packing_plan
from .services import QuoteChanged, create_order
from .shipping import quote_delivery, verified_delivery
from .test_cdek import CDEK_SETTINGS, PICKUP
from .test_support import checkout_data, fixture_cart


class AutoFixtures:
    def box(self, code="auto-box", **kwargs):
        box = PackingBox.objects.create(
            **{
                "code": code,
                "name": code,
                "inner_length_mm": 220,
                "inner_width_mm": 160,
                "inner_height_mm": 160,
                "outer_length_mm": 231,
                "outer_width_mm": 171,
                "outer_height_mm": 171,
                "tare_weight_g": 80,
                "max_weight_g": 5000,
                "auto_enabled": True,
                "auto_filler_weight_g": 20,
                "auto_padding_mm": 5,
                "auto_price_mode": "included",
                **kwargs,
            }
        )
        if not box.auto_test_only:
            box.confirm_auto_measurements()
        return box

    def product(self, sku="auto-a", **kwargs):
        product = Product.objects.create(
            **{
                "sku": sku,
                "slug": sku,
                "name": sku,
                "price": Decimal("100.00"),
                "shipping_mode": "automatic",
                "unit_weight_g": 100,
                "unit_length_mm": 60,
                "unit_width_mm": 60,
                "unit_height_mm": 120,
                **kwargs,
            }
        )
        if not product.unit_test_only:
            product.confirm_auto_measurements()
        return product

    def cart(self, *pairs):
        cart = Cart.objects.create(session_key="auto-cart")
        for product, quantity in pairs:
            CartItem.objects.create(cart=cart, product=product, quantity=quantity)
        return cart

    def assert_complete(self, plan, pairs):
        totals = Counter()
        for parcel in plan["parcels"]:
            for row in parcel["contents"]:
                totals[row["product_id"]] += row["quantity"]
            placements = parcel["placements"]
            self.assertEqual(len(placements), sum(row["quantity"] for row in parcel["contents"]))
            box = PackingBox.objects.get(code=parcel["box_code"])
            for i, placement in enumerate(placements):
                for axis, name in enumerate(("length", "width", "height")):
                    self.assertGreaterEqual(placement["position_mm"][axis], box.auto_padding_mm)
                    self.assertLessEqual(
                        placement["position_mm"][axis] + placement["size_mm"][axis],
                        getattr(box, f"inner_{name}_mm") - box.auto_padding_mm,
                    )
                for other in placements[i + 1 :]:
                    self.assertTrue(
                        any(
                            placement["position_mm"][a] + placement["size_mm"][a] <= other["position_mm"][a]
                            or other["position_mm"][a] + other["size_mm"][a] <= placement["position_mm"][a]
                            for a in range(3)
                        ),
                        "Protected envelopes overlap",
                    )
        self.assertEqual(totals, Counter({p.pk: q for p, q in pairs}))


@override_settings(CDEK_TEST_MODE=False)
class AutomaticPackingTests(AutoFixtures, TestCase):
    def test_two_different_products_share_box_and_weight_includes_materials(self):
        self.box()
        a, b = self.product(), self.product("auto-b", unit_weight_g=150)
        plan = packing_plan(self.cart((a, 1), (b, 1)))
        self.assertEqual(plan["packages"], [{"weight": 350, "length": 24, "width": 18, "height": 18}])
        self.assertTrue(plan["measurements_confirmed"])
        self.assertFalse(plan["parcels"][0]["assembly_measured"])
        self.assert_complete(plan, [(a, 1), (b, 1)])

    def test_one_shared_box_is_preferred_to_two_small_boxes(self):
        self.box(
            "small",
            inner_length_mm=90,
            inner_width_mm=90,
            inner_height_mm=130,
            outer_length_mm=100,
            outer_width_mm=100,
            outer_height_mm=140,
        )
        self.box("shared")
        a = self.product()
        plans = packing_options(self.cart((a, 2)))
        self.assertTrue(all(len(p["packages"]) == 1 for p in plans))
        self.assertEqual(plans[0]["parcels"][0]["box_code"], "shared")
        self.assert_complete(plans[0], [(a, 2)])

    def test_volume_alone_does_not_prove_fit(self):
        self.box(inner_length_mm=100, inner_width_mm=100, inner_height_mm=100, auto_padding_mm=0)
        a = self.product(unit_height_mm=60, unit_stack_limit_g=1000)
        plan = packing_plan(self.cart((a, 2)))
        self.assertEqual(len(plan["packages"]), 2)
        self.assert_complete(plan, [(a, 2)])

    def test_turning_on_side_requires_explicit_permission(self):
        self.box(inner_length_mm=130, inner_width_mm=80, inner_height_mm=50, auto_padding_mm=0)
        a = self.product(unit_width_mm=40)
        cart = self.cart((a, 1))
        with self.assertRaises(DeliveryUnavailable):
            packing_plan(cart)
        a.unit_allow_rotation = True
        a.confirm_auto_measurements()
        plan = packing_plan(cart)
        self.assertEqual(plan["parcels"][0]["placements"][0]["size_mm"][2], 40)
        self.assert_complete(plan, [(a, 1)])

    def test_stack_load_includes_every_unit_above(self):
        self.box(
            inner_length_mm=70, inner_width_mm=70, inner_height_mm=400, auto_padding_mm=0, outer_height_mm=410
        )
        a = self.product(unit_stack_limit_g=100)
        plan = packing_plan(self.cart((a, 3)))
        self.assertEqual(len(plan["packages"]), 2)
        self.assert_complete(plan, [(a, 3)])

    def test_groups_do_not_share_box(self):
        self.box()
        a, b = self.product(), self.product("auto-b", unit_packing_group="other")
        plan = packing_plan(self.cart((a, 1), (b, 1)))
        self.assertEqual(len(plan["packages"]), 2)
        self.assert_complete(plan, [(a, 1), (b, 1)])

    def test_pvz_limit_splits_by_gross_weight(self):
        self.box()
        a = self.product()
        plans = packing_options(self.cart((a, 3)), pickup={"weight_min_g": "0", "weight_max_g": "250"})
        self.assertEqual(len(plans[0]["packages"]), 3)
        self.assertTrue(all(p["weight"] == 200 for p in plans[0]["packages"]))
        self.assert_complete(plans[0], [(a, 3)])

    def test_changed_unit_invalidates_confirmation_and_fingerprint(self):
        self.box()
        a = self.product()
        cart = self.cart((a, 1))
        before = packing_configuration(cart)
        Product.objects.filter(pk=a.pk).update(unit_weight_g=101)
        self.assertNotEqual(before, packing_configuration(cart))
        with self.assertRaisesMessage(DeliveryUnavailable, "не подтверждены"):
            packing_plan(cart)

    def test_changed_box_invalidates_confirmation_and_fingerprint(self):
        box = self.box()
        cart = self.cart((self.product(), 1))
        before = packing_configuration(cart)
        PackingBox.objects.filter(pk=box.pk).update(auto_padding_mm=6)
        self.assertNotEqual(before, packing_configuration(cart))
        with self.assertRaises(DeliveryUnavailable):
            packing_plan(cart)

    def test_adding_available_box_invalidates_quote_dependencies(self):
        self.box()
        cart = self.cart((self.product(), 1))
        before = packing_configuration(cart)
        self.box("alternative")
        self.assertNotEqual(before, packing_configuration(cart))

    def test_demo_never_enables_live_checkout(self):
        box = self.box(auto_test_only=True)
        a = self.product(unit_test_only=True)
        cart = self.cart((a, 2))
        for obj in (a, box):
            with self.assertRaises(ValidationError):
                obj.confirm_auto_measurements()
        with self.assertRaises(DeliveryUnavailable):
            packing_plan(cart, test_mode=True)
        with override_settings(CDEK_TEST_MODE=True):
            plan = packing_plan(cart)
            self.assertFalse(plan["measurements_confirmed"])
            self.assertEqual(len(plan["packages"]), 1)

    def test_test_flag_cannot_revive_old_confirmation(self):
        box = self.box()
        for obj, field in ((box, "auto_test_only"), (self.product(), "unit_test_only")):
            setattr(obj, field, True)
            obj.save(update_fields=[field])
            setattr(obj, field, False)
            obj.save(update_fields=[field])
            self.assertFalse(obj.auto_measurements_valid)

    def test_readiness_recognizes_verified_automatic_singleton(self):
        self.box()
        a = self.product()
        self.assertEqual(packing_coverage([a]), [])

    def test_price_confirmation_survives_database_decimal_normalization(self):
        box = self.box(auto_price_mode="charge", auto_price=Decimal("45.5"))
        box.refresh_from_db()
        self.assertTrue(box.auto_measurements_valid)

    def test_non_stackable_floor_bound_prevents_expensive_impossible_search(self):
        unit = {
            "dimensions": (6, 6, 10),
            "weight": 1,
            "rotate": False,
            "stack_limit": 0,
            "product_id": 1,
            "number": 0,
        }
        units = [{**unit, "number": n} for n in range(4)]
        self.assertIsNone(fit_all(units, (10, 10, 100), 100, Budget(attempts=0)))

    def test_quantity_limit_is_enforced_before_expansion(self):
        with self.assertRaises(DeliveryUnavailable):
            AutomaticPacking([SimpleNamespace(product=self.product(), quantity=1000000)])

    def test_geometry_budget_fails_closed(self):
        unit = {
            "dimensions": (1, 1, 1),
            "weight": 1,
            "rotate": True,
            "stack_limit": 0,
            "product_id": 1,
            "number": 0,
        }
        with self.assertRaises(SearchLimit):
            fit_all([unit], (10, 10, 10), 100, Budget(attempts=0))


@override_settings(**{**CDEK_SETTINGS, "CDEK_TEST_MODE": False})
class AutomaticCheckoutTests(AutoFixtures, TestCase):
    def setUp(self):
        self.cart_obj, self.a, self.method = fixture_cart(quantity=2, stock=10)
        self.a.shipping_mode = "automatic"
        self.a.unit_weight_g = 100
        self.a.unit_length_mm, self.a.unit_width_mm, self.a.unit_height_mm = 60, 60, 120
        self.a.confirm_auto_measurements()
        self.box_obj = self.box()
        self.method.type, self.method.cdek_tariff_code = "cdek_pvz", 136
        self.method.save()
        self.provider = Mock()
        self.provider.pickup.return_value = copy.deepcopy(PICKUP)
        self.provider.calculate.return_value = {"price": "402.21", "period_min": 2, "period_max": 2}
        boundary = patch("apps.orders.shipping.CdekClient", return_value=self.provider)
        boundary.start()
        self.addCleanup(boundary.stop)

    def quote(self):
        return quote_delivery(self.cart_obj, self.method, "TEST1", self.cart_obj.session_key)

    def test_shared_parcel_sent_to_carrier_and_saved_with_placement(self):
        result = self.quote()
        self.provider.calculate.assert_called_once_with(
            136,
            PICKUP,
            [{"weight": 300, "length": 24, "width": 18, "height": 18}],
            declared_value=Decimal("200.00"),
        )
        order = create_order(
            self.cart_obj,
            checkout_data(
                self.cart_obj,
                self.method,
                quote_token=result["quote_token"],
                delivery_quote=result["delivery_quote"],
                pvz_code="TEST1",
            ),
            self.cart_obj.session_key,
        )
        self.assertEqual(order.total, Decimal("602.21"))
        self.assertEqual(order.delivery_snapshot["packing"]["parcels"][0]["contents"][0]["quantity"], 2)
        self.assertEqual(len(order.delivery_snapshot["packing"]["parcels"][0]["placements"]), 2)
        self.assertEqual(order.delivery_snapshot["packing_comparison"]["scope"], "bounded_automatic_options")

    def test_changed_box_after_quote_is_rejected(self):
        result = self.quote()
        PackingBox.objects.filter(pk=self.box_obj.pk).update(active=False)
        with self.assertRaises(QuoteChanged):
            verified_delivery(self.cart_obj, self.method, result["delivery_quote"], "TEST1")

    def test_edit_during_carrier_call_is_rejected(self):
        def changed(*args, **kwargs):
            Product.objects.filter(pk=self.a.pk).update(unit_stack_limit_g=500)
            return {"price": "402.21", "period_min": 2, "period_max": 2}

        self.provider.calculate.side_effect = changed
        with self.assertRaises(QuoteChanged):
            self.quote()

    def test_packaging_charge_is_in_delivery_total_but_not_declared_goods_value(self):
        self.box_obj.auto_price_mode = "charge"
        self.box_obj.auto_price = Decimal("45.50")
        self.box_obj.confirm_auto_measurements()
        result = self.quote()
        self.assertEqual(result["shipping"]["carrier_price"], "402.21")
        self.assertEqual(result["shipping"]["packing_price"], "45.50")
        self.assertEqual(result["shipping"]["price"], "447.71")
        self.assertEqual(result["total"], "647.71")
        self.assertEqual(self.provider.calculate.call_args.kwargs["declared_value"], Decimal("200.00"))
        order = create_order(
            self.cart_obj,
            checkout_data(
                self.cart_obj,
                self.method,
                quote_token=result["quote_token"],
                delivery_quote=result["delivery_quote"],
                pvz_code="TEST1",
            ),
            self.cart_obj.session_key,
        )
        self.assertEqual(order.delivery_price, Decimal("447.71"))
        from apps.payments.services import payment_payload

        order.items.update(vat_code=6)
        order.delivery_vat_code = 6
        with override_settings(ALFABANK_RECEIPT_MODE="bank", ALFABANK_TAX_SYSTEM=1):
            payload = payment_payload(order)
        receipt = json.loads(payload["orderBundle"])["cartItems"]["items"]
        self.assertEqual(payload["amount"], 64771)
        self.assertEqual(sum(item["itemAmount"] for item in receipt), payload["amount"])
        self.assertEqual(receipt[-1]["itemAmount"], 44771)
        self.assertIn("Доставка и упаковка", receipt[-1]["name"])

    def test_identical_boxes_with_different_packing_prices_keep_cheaper_option(self):
        self.box_obj.auto_price_mode = "charge"
        self.box_obj.auto_price = Decimal("90.00")
        self.box_obj.confirm_auto_measurements()
        self.box("cheaper", auto_price_mode="charge", auto_price=Decimal("10.00"))
        result = self.quote()
        self.assertEqual(result["shipping"]["price"], "412.21")
        self.assertEqual(result["shipping"]["packing"]["parcels"][0]["box_code"], "cheaper")

    def test_packaging_price_change_invalidates_quote(self):
        result = self.quote()
        PackingBox.objects.filter(pk=self.box_obj.pk).update(auto_price_mode="charge", auto_price="12.00")
        with self.assertRaises(QuoteChanged):
            verified_delivery(self.cart_obj, self.method, result["delivery_quote"], "TEST1")

    def test_charge_is_per_box_not_per_product_or_per_order(self):
        self.cart_obj.items.update(quantity=4)
        self.box_obj.auto_price_mode = "charge"
        self.box_obj.auto_price = Decimal("45.50")
        self.box_obj.confirm_auto_measurements()
        self.provider.pickup.return_value["weight_max_g"] = 300
        result = self.quote()
        self.assertEqual(len(result["shipping"]["packages"]), 2)
        self.assertEqual(result["shipping"]["packing_price"], "91.00")
        self.assertEqual(result["shipping"]["price"], "493.21")
        self.assertEqual(result["total"], "893.21")
        order = create_order(
            self.cart_obj,
            checkout_data(
                self.cart_obj,
                self.method,
                quote_token=result["quote_token"],
                delivery_quote=result["delivery_quote"],
                pvz_code="TEST1",
            ),
            self.cart_obj.session_key,
        )
        self.assertEqual(order.delivery_price, Decimal("493.21"))
        self.assertEqual(order.delivery_snapshot["packing_price"], "91.00")
        self.assertEqual(self.provider.calculate.call_args.kwargs["declared_value"], Decimal("400.00"))

    def test_missing_box_price_blocks_quote_instead_of_becoming_free(self):
        self.box_obj.auto_price_mode = "charge"
        self.box_obj.auto_price = None
        self.box_obj.save()
        with self.assertRaises(ValidationError):
            self.box_obj.confirm_auto_measurements()
        with self.assertRaises(DeliveryUnavailable):
            self.quote()
        self.provider.calculate.assert_not_called()


@override_settings(CDEK_TEST_MODE=False)
class PackingSetupTests(TestCase):
    def setup_examples(self):
        call_command("setup_auto_packing", with_demo=True, stdout=StringIO())

    def test_catalog_drafts_and_demo_are_isolated_and_repeatable(self):
        self.setup_examples()
        self.assertEqual(PackingBox.objects.filter(supplier="cdek", active=False).count(), 5)
        self.assertEqual(
            PackingBox.objects.filter(supplier="cdek", auto_price_mode="charge", auto_price=None).count(), 5
        )
        self.assertEqual(PackingBox.objects.filter(auto_test_only=True).count(), 3)
        self.assertEqual(
            Product.objects.filter(status="draft", purchasable=False, unit_test_only=True).count(), 2
        )
        self.assertFalse(PackingBox.objects.exclude(auto_measurement_signature="").exists())
        before = list(PackingBox.objects.order_by("pk").values())
        self.setup_examples()
        self.assertEqual(list(PackingBox.objects.order_by("pk").values()), before)

    def test_draft_with_unknown_measurements_can_be_saved_but_not_activated(self):
        self.setup_examples()
        box = PackingBox.objects.get(code="cdek-posylochka-xs")
        box.full_clean()
        box.active = True
        with self.assertRaises(ValidationError):
            box.full_clean()
        with self.assertRaises(ValidationError):
            box.confirm_auto_measurements()

    def test_setup_never_overwrites_real_records(self):
        self.setup_examples()
        product = Product.objects.get(sku="DEMO-AUTO-A")
        product.unit_test_only = False
        product.save()
        before = list(Product.objects.order_by("pk").values())
        with self.assertRaises(CommandError):
            self.setup_examples()
        self.assertEqual(list(Product.objects.order_by("pk").values()), before)

    def test_policy_upgrade_preserves_prices_and_configured_profiles(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection

        self.setup_examples()
        changed = PackingBox.objects.get(code="cdek-posylochka-xs")
        changed.auto_price_mode = ""
        changed.auto_price = Decimal("50.00")
        changed.save()
        explicit = PackingBox.objects.get(code="cdek-posylochka-s")
        explicit.auto_price_mode = "included"
        explicit.save()
        untouched = list(PackingBox.objects.exclude(pk=changed.pk).order_by("pk").values())
        migration = import_module("apps.orders.migrations.0013_charge_for_cdek_boxes")
        migration.set_cdek_charging(apps, SimpleNamespace(connection=connection))
        changed.refresh_from_db()
        self.assertEqual(changed.auto_price_mode, "charge")
        self.assertEqual(changed.auto_price, Decimal("50.00"))
        self.assertFalse(changed.active)
        self.assertFalse(changed.auto_measurements_valid)
        self.assertEqual(list(PackingBox.objects.exclude(pk=changed.pk).order_by("pk").values()), untouched)

    def test_demo_preview_is_explicit_and_does_not_create_cart_or_order(self):
        from .models import Order

        self.setup_examples()
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "preview_auto_packing", "--item", "DEMO-AUTO-A:1", "--item", "DEMO-AUTO-B:1", stdout=output
            )
        call_command(
            "preview_auto_packing",
            "--item",
            "DEMO-AUTO-A:1",
            "--item",
            "DEMO-AUTO-B:1",
            test_data=True,
            stdout=output,
        )
        result = json.loads(output.getvalue())
        self.assertTrue(result["preview_only"])
        self.assertFalse(result["shipment_created"])
        plan = result["options"][0]["packing"]
        self.assertEqual(len(plan["packages"]), 1)
        self.assertEqual(plan["parcels"][0]["box_code"], "demo-auto-shared")
        self.assertFalse(plan["measurements_confirmed"])
        self.assertEqual(Cart.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)

    def test_manager_can_read_new_fields_in_native_admin(self):
        from django.contrib.auth import get_user_model

        self.setup_examples()
        user = get_user_model().objects.create_superuser(username="auto-owner", password="test-only")
        self.client.defaults["HTTP_HOST"] = "shop.localhost"
        self.client.force_login(user)
        box = PackingBox.objects.get(code="cdek-posylochka-xs")
        response = self.client.get(f"/admin/orders/packingbox/{box.pk}/change/")
        self.assertContains(response, "Автоматический подбор")
        self.assertContains(response, "Справочные сведения поставщика")
        product = Product.objects.get(sku="DEMO-AUTO-A")
        response = self.client.get(f"/admin/catalog/product/{product.pk}/change/")
        self.assertContains(response, "Допустимый вес сверху")
        self.assertContains(response, "Параметры автоподбора")

    def test_admin_confirms_inputs_and_later_edits_require_reconfirmation(self):
        from django.contrib.auth import get_user_model

        self.setup_examples()
        self.client.defaults["HTTP_HOST"] = "shop.localhost"
        self.client.force_login(get_user_model().objects.create_superuser(username="packing-owner"))

        def submit(url, changes):
            page = self.client.get(url)
            form = page.context["adminform"].form
            data = {name: field.value() for name in form.fields if (field := form[name]).value() is not None}
            for inline in page.context["inline_admin_formsets"]:
                management = inline.formset.management_form
                data.update({field.html_name: field.value() for field in management})
            data.update(changes)
            return self.client.post(url, data)

        box = PackingBox.objects.get(code="demo-auto-shared")
        product = Product.objects.get(sku="DEMO-AUTO-A")
        for obj, path, test_flag, changed_field in (
            (box, "orders/packingbox", "auto_test_only", "auto_filler_weight_g"),
            (product, "catalog/product", "unit_test_only", "unit_weight_g"),
        ):
            url = f"/admin/{path}/{obj.pk}/change/"
            response = submit(url, {test_flag: "", "confirm_auto_measurements": "on"})
            self.assertEqual(response.status_code, 302, getattr(response, "context", None))
            obj.refresh_from_db()
            self.assertTrue(obj.auto_measurements_valid)
            response = submit(url, {changed_field: getattr(obj, changed_field) + 1})
            self.assertEqual(response.status_code, 302, getattr(response, "context", None))
            obj.refresh_from_db()
            self.assertFalse(obj.auto_measurements_valid)
