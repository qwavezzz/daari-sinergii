from io import StringIO
from unittest import skipIf, skipUnless

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings

from apps.catalog.models import Product
from apps.orders.models import DeliveryMethod, PackingBox, PackingRecipe, StoreSettings


@override_settings(DEBUG=True, PAYMENT_STUB_ENABLED=True, ALFABANK_ENABLED=False, CDEK_TEST_MODE=True)
@skipUnless(
    connection.vendor == "sqlite", "Local demo commands require SQLite; covered in the SQLite CI step."
)
class WorkingCheckoutSetupTests(TestCase):
    def test_setup_opens_rehearsal_and_preserves_real_products(self):
        demo = Product.objects.create(name="Учебный", slug="demo", sku="DEMO-001", price=100, stock=5)
        real = Product.objects.create(name="Реальный", slug="real", sku="REAL-001", price=200, stock=4)
        call_command("setup_working_checkout", stdout=StringIO())
        call_command("setup_working_checkout", stdout=StringIO())
        self.assertTrue(StoreSettings.objects.get(pk=1).checkout_enabled)
        method = DeliveryMethod.objects.get(slug="cdek-local-rehearsal")
        self.assertEqual((method.type, method.cdek_tariff_code, method.active), ("cdek_pvz", 136, True))
        demo.refresh_from_db()
        real.refresh_from_db()
        self.assertEqual(demo.package_weight_g, 400)
        self.assertIsNone(real.package_weight_g)
        self.assertEqual((demo.stock, real.stock), (5, 4))

    @override_settings(DEBUG=False)
    def test_setup_refuses_production_before_writing(self):
        with self.assertRaises(CommandError):
            call_command("setup_working_checkout", stdout=StringIO())
        self.assertFalse(StoreSettings.objects.exists())
        self.assertFalse(DeliveryMethod.objects.exists())

    @override_settings(ALFABANK_ENABLED=True)
    def test_setup_refuses_bank_enabled(self):
        with self.assertRaises(CommandError):
            call_command("setup_working_checkout", stdout=StringIO())
        self.assertFalse(StoreSettings.objects.exists())


@override_settings(DEBUG=True, PAYMENT_STUB_ENABLED=True, ALFABANK_ENABLED=False, CDEK_TEST_MODE=True)
@skipIf(connection.vendor == "sqlite", "Exercises refusal on a real non-SQLite test database.")
class LocalRehearsalDatabaseGuardTests(TestCase):
    def test_local_commands_refuse_non_sqlite_before_writing(self):
        Product.objects.create(name="Учебный", slug="demo", sku="DEMO-001", price=100, stock=5)
        models = (Product, DeliveryMethod, StoreSettings, PackingBox, PackingRecipe)
        before = {model: list(model.objects.order_by("pk").values()) for model in models}
        for command in ("setup_working_checkout", "seed_demo_shipping"):
            with self.subTest(command=command):
                with self.assertRaises(CommandError):
                    call_command(command, stdout=StringIO())
                for model in models:
                    self.assertEqual(before[model], list(model.objects.order_by("pk").values()))
