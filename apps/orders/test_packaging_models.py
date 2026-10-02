from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.admin import ProductAdminForm
from apps.catalog.models import Product
from .models import PackingBox, PackingRecipe, PackingRecipeItem


class PackingFixtures:
    def setUp(self):
        # Synthetic fixtures only; no real catalogue measurements are seeded.
        self.product = Product.objects.create(
            name="Тестовый флакон",
            slug="packing-test",
            sku="PACKING-TEST",
            shipping_mode=Product.ShippingMode.COMBINED,
            unit_weight_g=200,
            unit_length_mm=50,
            unit_width_mm=50,
            unit_height_mm=100,
        )
        self.box = PackingBox.objects.create(
            name="Тестовая коробка",
            code="packing-test",
            inner_length_mm=150,
            inner_width_mm=120,
            inner_height_mm=110,
            outer_length_mm=160,
            outer_width_mm=130,
            outer_height_mm=120,
            tare_weight_g=80,
            max_weight_g=2000,
        )
        self.recipe = PackingRecipe.objects.create(
            name="Два тестовых флакона",
            box=self.box,
            packing_weight_g=20,
            measured_weight_g=500,
            outer_length_mm=160,
            outer_width_mm=130,
            outer_height_mm=120,
            instructions="Два защищённых флакона вертикально, между ними разделитель.",
        )
        self.item = PackingRecipeItem.objects.create(recipe=self.recipe, product=self.product, quantity=2)


class MeasuredPackingModelTests(PackingFixtures, TestCase):
    def test_plain_save_never_confirms_and_confirmation_does_not_activate(self):
        self.assertFalse(self.recipe.measurements_valid)
        self.recipe.confirm_measurements()
        self.recipe.refresh_from_db()
        self.assertTrue(self.recipe.measurements_valid)
        self.assertFalse(self.recipe.active)
        self.assertIsNotNone(self.recipe.measured_at)

    def test_draft_can_be_saved_without_measurements_but_not_confirmed(self):
        draft = PackingRecipe(name="Будущая схема", box=self.box)
        draft.full_clean()
        draft.save()
        with self.assertRaises(ValidationError) as error:
            draft.confirm_measurements()
        self.assertIn("Добавьте товары", " ".join(error.exception.messages))
        self.assertFalse(draft.measurements_valid)

    def test_changed_protected_unit_invalidates_even_prefetched_recipe(self):
        self.recipe.confirm_measurements()
        recipe = PackingRecipe.objects.prefetch_related("items__product").get(pk=self.recipe.pk)
        Product.objects.filter(pk=self.product.pk).update(unit_length_mm=51)
        self.assertFalse(recipe.measurements_valid)

    def test_changed_box_invalidates_even_cached_relation(self):
        self.recipe.confirm_measurements()
        recipe = PackingRecipe.objects.select_related("box").get(pk=self.recipe.pk)
        PackingBox.objects.filter(pk=self.box.pk).update(inner_length_mm=149)
        self.assertFalse(recipe.measurements_valid)

    def test_changed_quantity_or_instructions_requires_confirmation(self):
        self.recipe.confirm_measurements()
        self.item.quantity = 1
        self.item.save(update_fields=["quantity"])
        self.assertFalse(self.recipe.measurements_valid)
        self.recipe.confirm_measurements()
        self.recipe.instructions += " Дополнительная прокладка."
        self.assertFalse(self.recipe.measurements_valid)

    def test_direct_database_update_invalidates_already_loaded_recipe(self):
        self.recipe.confirm_measurements()
        PackingRecipe.objects.filter(pk=self.recipe.pk).update(measured_weight_g=501)
        self.assertFalse(self.recipe.measurements_valid)

    def test_loaded_snapshot_validates_without_database_queries(self):
        self.recipe.confirm_measurements()
        recipe = (
            PackingRecipe.objects.select_related("box")
            .prefetch_related("items__product")
            .get(pk=self.recipe.pk)
        )
        rows = list(recipe.items.all())
        expected_payload = recipe.measurement_payload()
        with self.assertNumQueries(0):
            self.assertEqual(recipe.validate_measurements(box=recipe.box, rows=rows), expected_payload)
            self.assertTrue(recipe.measurements_valid_for_snapshot(box=recipe.box, rows=rows))

    def test_snapshot_signature_checks_loaded_physical_values(self):
        self.recipe.confirm_measurements()
        rows = list(self.recipe.items.select_related("product"))
        rows[0].product.unit_length_mm += 1
        with self.assertNumQueries(0):
            self.assertFalse(self.recipe.measurements_valid_for_snapshot(box=self.box, rows=rows))
        # Editing only the in-memory snapshot must not change persisted data.
        self.assertTrue(self.recipe.measurements_valid)

    def test_snapshot_rejects_relations_from_another_recipe_or_box(self):
        rows = list(self.recipe.items.select_related("product"))
        with self.assertRaises(ValueError):
            self.recipe.validate_measurements(box=self.box)
        self.box.pk += 1
        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            self.recipe.validate_measurements(box=self.box, rows=rows)
        self.box.pk -= 1
        rows[0].recipe_id += 1
        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            self.recipe.validate_measurements(box=self.box, rows=rows)

    def test_test_only_recipe_never_confirms_physical_measurements(self):
        self.recipe.test_only = True
        self.recipe.save(update_fields=["test_only"])
        self.assertTrue(self.recipe.validate_measurements()["test_only"])
        with self.assertRaisesMessage(ValidationError, "Учебную схему нельзя подтвердить"):
            self.recipe.confirm_measurements()
        self.recipe.refresh_from_db()
        self.assertFalse(self.recipe.measurements_valid)
        self.assertEqual(self.recipe.measurement_signature, "")
        self.assertIsNone(self.recipe.measured_at)

    def test_changing_test_flag_requires_new_confirmation_after_real_assembly(self):
        self.recipe.confirm_measurements()
        original_signature = self.recipe.measurement_signature
        original_payload = self.recipe.measurement_payload()
        self.recipe.test_only = True
        self.recipe.save(update_fields=["test_only"])
        self.recipe.refresh_from_db()
        self.assertNotEqual(self.recipe.measurement_payload(), original_payload)
        self.assertEqual(self.recipe.measurement_signature, "")
        self.assertIsNone(self.recipe.measured_at)
        self.recipe.test_only = False
        self.recipe.save(update_fields=["test_only"])
        self.assertFalse(self.recipe.measurements_valid)
        self.recipe.confirm_measurements()
        self.assertTrue(self.recipe.measurements_valid)
        self.assertEqual(self.recipe.measurement_signature, original_signature)

    def test_persisted_test_flag_invalidates_cached_real_recipe(self):
        self.recipe.confirm_measurements()
        PackingRecipe.objects.filter(pk=self.recipe.pk).update(test_only=True)
        self.assertFalse(self.recipe.measurements_valid)

    def test_unit_measurements_must_be_complete_and_combined(self):
        for changes in ({"unit_height_mm": None}, {"shipping_mode": "individual"}):
            with self.subTest(changes=changes):
                Product.objects.filter(pk=self.product.pk).update(**changes)
                with self.assertRaises(ValidationError):
                    self.recipe.confirm_measurements()
                Product.objects.filter(pk=self.product.pk).update(
                    unit_height_mm=100, shipping_mode="combined"
                )

    def test_impossible_physical_measurements_are_rejected(self):
        cases = [
            ("measured_weight_g", 496, "меньше суммы"),
            ("measured_weight_g", 2001, "предельный вес"),
            ("outer_length_mm", 140, "меньше размеров"),
            ("instructions", "   ", "порядок сборки"),
        ]
        for field, value, message in cases:
            with self.subTest(field=field, value=value):
                recipe = PackingRecipe.objects.get(pk=self.recipe.pk)
                setattr(recipe, field, value)
                with self.assertRaisesMessage(ValidationError, message):
                    recipe.confirm_measurements()

    def test_component_rounding_does_not_force_inflated_measured_gross(self):
        # Three units of 100.1 g, a 50.1 g box and 10.1 g filler weigh 360.5 g.
        # Their separately rounded fields add up to 365 g, but gross is 361 g.
        Product.objects.filter(pk=self.product.pk).update(unit_weight_g=101)
        PackingRecipeItem.objects.filter(pk=self.item.pk).update(quantity=3)
        PackingBox.objects.filter(pk=self.box.pk).update(tare_weight_g=51)
        self.recipe.packing_weight_g = 11
        self.recipe.measured_weight_g = 361
        self.recipe.confirm_measurements()
        self.recipe.refresh_from_db()
        self.assertTrue(self.recipe.measurements_valid)
        self.assertEqual(self.recipe.measured_weight_g, 361)
        self.assertEqual(self.recipe.measurement_payload()["measured_weight_g"], 361)
        self.recipe.measured_weight_g = 360
        with self.assertRaisesMessage(ValidationError, "с учётом округления"):
            self.recipe.confirm_measurements()

    def test_zero_filler_does_not_increase_rounding_allowance(self):
        # Two units and one box: at most 2 g between the rounded sums.
        self.recipe.packing_weight_g = 0
        self.recipe.measured_weight_g = 478
        self.recipe.confirm_measurements()
        self.assertTrue(self.recipe.measurements_valid)
        self.recipe.measured_weight_g = 477
        with self.assertRaisesMessage(ValidationError, "меньше суммы"):
            self.recipe.confirm_measurements()

    def test_diagonal_arrangement_is_not_rejected_by_axis_aligned_dimensions(self):
        Product.objects.filter(pk=self.product.pk).update(unit_height_mm=151)
        self.recipe.confirm_measurements()
        self.assertTrue(self.recipe.measurements_valid)
        self.assertIn("вдоль сторон", " ".join(self.recipe.geometry_notes()))

    def test_bounding_volume_is_informational_and_does_not_disprove_real_assembly(self):
        PackingRecipeItem.objects.filter(pk=self.item.pk).update(quantity=8)
        self.recipe.measured_weight_g = 1700
        self.recipe.confirm_measurements()
        self.assertTrue(self.recipe.measurements_valid)
        self.assertIn("прямоугольных габаритов", " ".join(self.recipe.geometry_notes()))

    def test_outer_axes_may_be_reordered(self):
        self.recipe.outer_length_mm = 120
        self.recipe.outer_height_mm = 160
        self.recipe.confirm_measurements()
        self.assertTrue(self.recipe.measurements_valid)

    def test_inactive_box_disables_existing_verified_recipe(self):
        self.recipe.confirm_measurements()
        PackingBox.objects.filter(pk=self.box.pk).update(active=False)
        self.assertFalse(self.recipe.measurements_valid)

    def test_box_checks_geometry_and_gross_limit(self):
        self.box.inner_length_mm = 161
        self.box.max_weight_g = 80
        with self.assertRaises(ValidationError) as error:
            self.box.full_clean()
        self.assertIn("inner_length_mm", error.exception.message_dict)
        self.assertIn("max_weight_g", error.exception.message_dict)

    def test_recipe_items_reject_duplicate_and_zero_at_database_level(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PackingRecipeItem.objects.create(recipe=self.recipe, product=self.product, quantity=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PackingRecipeItem.objects.filter(pk=self.item.pk).update(quantity=0)

    def test_referenced_products_and_boxes_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.product.delete()
        with self.assertRaises(ProtectedError):
            self.box.delete()

    def test_individual_package_needs_explicit_confirmation_and_invalidates_after_edit(self):
        product = Product.objects.create(
            name="Отдельная тестовая посылка",
            slug="individual-test",
            sku="INDIVIDUAL-TEST",
            package_weight_g=300,
            package_length_cm=10,
            package_width_cm=10,
            package_height_cm=20,
        )
        self.assertFalse(product.package_measurements_valid)
        product.confirm_package_measurements()
        self.assertTrue(product.package_measurements_valid)
        Product.objects.filter(pk=product.pk).update(package_height_cm=21)
        self.assertFalse(product.package_measurements_valid)
        product.refresh_from_db()
        self.assertFalse(product.package_measurements_valid)
        product.confirm_package_measurements()
        self.assertTrue(product.package_measurements_valid)

    def test_individual_confirmation_rejects_unknown_dimensions(self):
        product = Product.objects.create(name="Без замеров", slug="unmeasured", sku="UNMEASURED")
        with self.assertRaises(ValidationError):
            product.confirm_package_measurements()


@override_settings(ROOT_URLCONF="config.shop_urls")
class PackingAdminTests(PackingFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser(username="packing-admin", password="test")
        self.client.defaults["HTTP_HOST"] = "shop.localhost"
        self.client.force_login(self.user)

    def test_native_admin_forms_expose_units_and_confirmation(self):
        urls = [
            (reverse("admin:catalog_product_change", args=[self.product.pk]), "Товар для общей коробки"),
            (reverse("admin:orders_packingbox_change", args=[self.box.pk]), "Внутренние размеры"),
            (
                reverse("admin:orders_packingrecipe_change", args=[self.recipe.pk]),
                "Подтверждение фактических замеров",
            ),
        ]
        for url, text in urls:
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), text)

    def test_action_errors_are_shown_without_confirming(self):
        self.recipe.instructions = ""
        self.recipe.save(update_fields=["instructions"])
        response = self.client.post(
            reverse("admin:orders_packingrecipe_changelist"),
            {
                "action": "confirm_actual_measurements",
                "_selected_action": [str(self.recipe.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            any("порядок сборки" in str(message) for message in get_messages(response.wsgi_request))
        )
        self.recipe.refresh_from_db()
        self.assertFalse(self.recipe.measurements_valid)

    def test_action_confirms_actual_assembly_and_logs_operator(self):
        response = self.client.post(
            reverse("admin:orders_packingrecipe_changelist"),
            {
                "action": "confirm_actual_measurements",
                "_selected_action": [str(self.recipe.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.recipe.refresh_from_db()
        self.assertTrue(self.recipe.measurements_valid)
        self.assertFalse(self.recipe.active)
        self.assertTrue(
            admin.models.LogEntry.objects.filter(user=self.user, object_id=str(self.recipe.pk)).exists()
        )

    def test_admin_labels_fiction_and_refuses_confirmation(self):
        self.recipe.test_only = True
        self.recipe.save(update_fields=["test_only"])
        response = self.client.get(reverse("admin:orders_packingrecipe_change", args=[self.recipe.pk]))
        self.assertContains(response, "Учебная схема — только тестовый СДЭК")
        self.assertContains(response, "Учебные параметры, не реальные замеры")
        response = self.client.post(
            reverse("admin:orders_packingrecipe_changelist"),
            {"action": "confirm_actual_measurements", "_selected_action": [str(self.recipe.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            any("Учебную схему нельзя подтвердить" in str(m) for m in get_messages(response.wsgi_request))
        )
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.measurement_signature, "")
        self.assertIsNone(self.recipe.measured_at)
        self.assertFalse(
            admin.models.LogEntry.objects.filter(user=self.user, object_id=str(self.recipe.pk)).exists()
        )

    def test_product_checkbox_validation_returns_field_errors(self):
        form = ProductAdminForm(
            data={
                "name": self.product.name,
                "sku": self.product.sku,
                "slug": self.product.slug,
                "status": "draft",
                "stock": 0,
                "sort_order": 0,
                "shipping_mode": "individual",
                "confirm_package_measurements": "on",
                "stock_snapshot": signing.dumps([self.product.pk, 0, 0], salt="admin-stock"),
            },
            instance=self.product,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("package_weight_g", form.errors)
        self.assertIn("package_height_cm", form.errors)

    def test_product_checkbox_confirms_after_saving_all_fields(self):
        url = reverse("admin:catalog_product_change", args=[self.product.pk])
        response = self.client.post(
            url,
            {
                "name": self.product.name,
                "sku": self.product.sku,
                "slug": self.product.slug,
                "status": "draft",
                "stock": 0,
                "sort_order": 0,
                "shipping_mode": "individual",
                "package_weight_g": 300,
                "package_length_cm": 10,
                "package_width_cm": 10,
                "package_height_cm": 20,
                "confirm_package_measurements": "on",
                "stock_snapshot": signing.dumps([self.product.pk, 0, 0], salt="admin-stock"),
                "images-TOTAL_FORMS": 0,
                "images-INITIAL_FORMS": 0,
                "images-MIN_NUM_FORMS": 0,
                "images-MAX_NUM_FORMS": 1000,
                "attributes-TOTAL_FORMS": 0,
                "attributes-INITIAL_FORMS": 0,
                "attributes-MIN_NUM_FORMS": 0,
                "attributes-MAX_NUM_FORMS": 1000,
                "_save": "Сохранить",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertTrue(self.product.package_measurements_valid)
