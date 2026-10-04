from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from apps.catalog.models import Product
from apps.orders.models import DeliveryMethod, StoreSettings
from apps.orders.services import create_order
from apps.orders.test_support import checkout_data, fixture_cart
from apps.payments.models import PaymentAttempt
from deploy.configure_rehearsal import configure_database, environment_text


class RehearsalEnvironmentTests(SimpleTestCase):
    def test_replaces_duplicate_flags_and_preserves_unrelated_private_values(self):
        original = (
            'DATABASE_URL="postgres://private-value"\n'
            "# owner comment\nPAYMENT_STUB_ENABLED=false\n"
            'PAYMENT_STUB_ENABLED="false"\nALFABANK_ENABLED=true\n'
            'EMAIL_HOST_PASSWORD="keep $literal value"\n'
        )
        result = environment_text(original, "public-id", "public-secret")
        self.assertIn('DATABASE_URL="postgres://private-value"', result)
        self.assertIn('EMAIL_HOST_PASSWORD="keep $literal value"', result)
        self.assertEqual(result.count("PAYMENT_STUB_ENABLED="), 1)
        self.assertIn("ALFABANK_ENABLED=false\n", result)
        self.assertIn("DJANGO_SETTINGS_MODULE=config.settings\n", result)
        self.assertNotIn("DEBUG=", result)
        self.assertEqual(environment_text(result, "public-id", "public-secret"), result)

    def test_rejects_multiline_target_and_unsafe_value(self):
        with self.assertRaises(ValueError):
            environment_text("CDEK_CLIENT_SECRET=abc\\\ncontinued\n", "public", "secret")
        with self.assertRaises(ValueError):
            environment_text("", "public", "secret\nOTHER=true")


@override_settings(
    DEBUG=False,
    DEVELOPMENT=False,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    CHECKOUT_ENABLED=True,
    PAYMENT_STUB_ENABLED=True,
    ALFABANK_ENABLED=False,
    ALFABANK_TEST_MODE=True,
    ALFABANK_LIVE_APPROVED=False,
    CDEK_ENABLED=True,
    CDEK_TEST_MODE=True,
)
class HostedRehearsalTests(TestCase):
    def setUp(self):
        self.cart, self.product, self.method = fixture_cart()
        self.product.sku = "DEMO-TEST"
        self.product.package_weight_g = 777
        self.product.save()
        StoreSettings.objects.filter(pk=1).update(checkout_enabled=False)

    def test_sets_up_only_demo_packages_preserving_owner_text_price_stock_and_real_drafts(self):
        draft = Product.objects.create(name="Real draft", sku="REAL", slug="real")
        configure_database()
        configure_database()
        store = StoreSettings.objects.get(pk=1)
        self.assertTrue(store.checkout_enabled)
        self.assertEqual(store.terms_text, "Утверждённые тестовые условия")
        self.product.refresh_from_db()
        self.assertEqual(self.product.package_weight_g, 777)
        self.assertEqual(self.product.package_length_cm, 20)
        self.assertEqual(self.product.price, 100)
        self.assertEqual(self.product.stock, 5)
        draft.refresh_from_db()
        self.assertIsNone(draft.package_weight_g)
        method = DeliveryMethod.objects.get(active=True)
        self.assertEqual(method.slug, "cdek-vps-rehearsal")
        self.assertTrue(method.is_default)
        self.assertEqual(method.cdek_tariff_code, 136)

    def test_rejects_real_catalog_before_mutation(self):
        self.product.sku = "REAL"
        self.product.save()
        with self.assertRaises(ValidationError):
            configure_database()
        self.assertFalse(StoreSettings.objects.get(pk=1).checkout_enabled)
        self.assertFalse(DeliveryMethod.objects.filter(slug="cdek-vps-rehearsal").exists())

    def test_rejects_bank_history(self):
        StoreSettings.objects.filter(pk=1).update(checkout_enabled=True)
        order = create_order(self.cart, checkout_data(self.cart, self.method), self.cart.session_key)
        PaymentAttempt.objects.create(order=order, amount=order.total)
        with self.assertRaises(ValidationError):
            configure_database()

    def test_rejects_unsafe_modes(self):
        for flag, value in [
            ("DEBUG", True),
            ("DEVELOPMENT", True),
            ("PAYMENT_STUB_ENABLED", False),
            ("ALFABANK_ENABLED", True),
            ("ALFABANK_LIVE_APPROVED", True),
            ("CDEK_TEST_MODE", False),
            ("SESSION_COOKIE_SECURE", False),
        ]:
            with self.subTest(flag=flag), override_settings(**{flag: value}):
                with self.assertRaises(ValidationError):
                    configure_database()

    def test_database_failure_rolls_back_customer_pages_and_delivery_changes(self):
        with patch.object(Product, "save", side_effect=RuntimeError("simulated failure")):
            with self.assertRaises(RuntimeError):
                configure_database()
        self.assertFalse(StoreSettings.objects.get(pk=1).checkout_enabled)
        self.assertFalse(DeliveryMethod.objects.filter(slug="cdek-vps-rehearsal").exists())
