from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings

from apps.catalog.models import Product, ProductAttribute, ProductImage
from apps.content.models import SiteSettings
from apps.core.acceptance import configuration_digest
from apps.core.management.commands.check_store_readiness import packing_coverage, readiness_issues
from apps.core.models import StoreAcceptance
from apps.orders.models import DeliveryMethod, PackingBox, PackingRecipe, StoreSettings


class LaunchReadinessTests(TestCase):
    @override_settings(
        DEVELOPMENT=False,
        DEBUG=False,
        SHOP_ORIGIN="https://shop.example.test",
        CHECKOUT_ENABLED=True,
        PAYMENT_STUB_ENABLED=False,
        CDEK_ENABLED=True,
        CDEK_TEST_MODE=False,
        CDEK_DEMO_QUOTES_ENABLED=False,
        CDEK_CLIENT_ID="fixture",
        CDEK_CLIENT_SECRET="fixture",
        CDEK_FROM_CITY_CODE=431,
        ALFABANK_ENABLED=True,
        ALFABANK_TEST_MODE=False,
        ALFABANK_LIVE_APPROVED=True,
        ALFABANK_USERNAME="fixture",
        ALFABANK_PASSWORD="fixture",
        ALFABANK_RECEIPT_MODE="bank",
        ALFABANK_TAX_SYSTEM=1,
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.test",
        EMAIL_HOST_USER="fixture",
        EMAIL_HOST_PASSWORD="fixture",
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_SSL_REDIRECT=True,
    )
    def test_complete_configuration_passes_but_missing_photo_or_fiscal_evidence_blocks(self):
        SiteSettings.objects.create(
            legal_name="Test seller",
            inn="123456789012",
            registration_number="123456789012345",
            address="Seller address",
            postal_address="Postal address",
            return_address="Returns",
            phone="+79990000000",
            email="shop@example.test",
        )
        StoreSettings.objects.create(
            checkout_enabled=True,
            terms_text="Terms",
            privacy_text="Privacy",
            delivery_text="Delivery",
            returns_text="Returns",
        )
        p = Product.objects.create(
            name="Measured",
            slug="measured",
            sku="MEASURED",
            description="Description",
            price=100,
            stock=5,
            status="published",
            purchasable=True,
            vat_code=1,
            package_weight_g=200,
            package_length_cm=10,
            package_width_cm=10,
            package_height_cm=10,
        )
        p.confirm_package_measurements()
        ProductAttribute.objects.create(product=p, name="Volume", value="100 ml")
        ProductImage.objects.create(product=p, image="fixture.png", alt="Product")
        DeliveryMethod.objects.create(
            name="CDEK", slug="cdek", type="cdek_pvz", price=0, cdek_tariff_code=136, active=True, vat_code=1
        )
        for kind in StoreAcceptance.Check.values:
            StoreAcceptance.objects.create(
                kind=kind,
                reference="External acceptance fixture",
                configuration_digest=configuration_digest(kind),
            )
        # Do not change the test DB connection: only the read-only preflight's view.
        proxy = SimpleNamespace(**{name: getattr(settings, name) for name in dir(settings) if name.isupper()})
        proxy.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql"}}
        storage = ProductImage._meta.get_field("image").storage
        with (
            patch("apps.core.management.commands.check_store_readiness.settings", proxy),
            patch.object(storage, "exists", return_value=True) as exists,
        ):
            self.assertEqual(readiness_issues("live"), [])
            exists.return_value = False
            self.assertTrue(any("фотографии отсутствует" in issue for issue in readiness_issues("live")))
            exists.return_value = True
            StoreAcceptance.objects.filter(kind="fiscal").delete()
            self.assertTrue(any("Чеки оплаты" in issue for issue in readiness_issues("live")))

    def test_review_does_not_require_bank_credentials_but_live_does(self):
        with override_settings(ALFABANK_USERNAME="", ALFABANK_PASSWORD="", PAYMENT_STUB_ENABLED=True):
            review = "\n".join(readiness_issues("review"))
            live = "\n".join(readiness_issues("live"))
        self.assertNotIn("ALFABANK_PASSWORD", review)
        self.assertIn("ALFABANK_PASSWORD", live)
        self.assertIn("PAYMENT_STUB_ENABLED", review)
        self.assertIn("протокола приёмки", review)
        self.assertIn("Чеки оплаты", live)

    def test_acceptance_expires_when_smtp_configuration_changes(self):
        StoreAcceptance.objects.create(
            kind="email", reference="Acceptance reference", configuration_digest=configuration_digest("email")
        )
        self.assertFalse(any("Письма получены" in issue for issue in readiness_issues("review")))
        with override_settings(EMAIL_HOST="changed.example.test"):
            self.assertTrue(any("Письма получены" in issue for issue in readiness_issues("review")))

    def test_individual_measurements_are_confirmed_and_invalidated_by_changes(self):
        p = Product.objects.create(
            name="Measured",
            slug="measured",
            sku="MEASURED",
            price=100,
            package_weight_g=200,
            package_length_cm=10,
            package_width_cm=10,
            package_height_cm=10,
        )
        self.assertEqual(packing_coverage([p]), [p])
        p.confirm_package_measurements()
        self.assertEqual(packing_coverage([p]), [])
        p.package_weight_g = 300
        p.save()
        self.assertEqual(packing_coverage([p]), [p])

    def test_combined_shipping_needs_confirmed_singleton_fallback(self):
        p = Product.objects.create(
            name="Measured",
            slug="measured",
            sku="MEASURED",
            price=100,
            shipping_mode="combined",
            unit_weight_g=100,
            unit_length_mm=30,
            unit_width_mm=30,
            unit_height_mm=30,
        )
        box = PackingBox.objects.create(
            code="box",
            name="Box",
            inner_length_mm=100,
            inner_width_mm=100,
            inner_height_mm=100,
            outer_length_mm=110,
            outer_width_mm=110,
            outer_height_mm=110,
            tare_weight_g=100,
            max_weight_g=1000,
            active=True,
        )
        recipe = PackingRecipe.objects.create(
            name="One",
            box=box,
            measured_weight_g=220,
            packing_weight_g=20,
            outer_length_mm=110,
            outer_width_mm=110,
            outer_height_mm=110,
            instructions="Measured packing procedure",
            active=True,
        )
        recipe.items.create(product=p, quantity=1)
        self.assertEqual(packing_coverage([p]), [p])
        recipe.confirm_measurements()
        self.assertEqual(packing_coverage([p]), [])
        box.tare_weight_g = 150
        box.save()
        self.assertEqual(packing_coverage([p]), [p])
        box.tare_weight_g = 100
        box.save()
        recipe.test_only = True
        recipe.save()
        self.assertEqual(packing_coverage([p]), [p])
