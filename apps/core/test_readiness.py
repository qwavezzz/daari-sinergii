from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from apps.catalog.models import Product
from apps.core.middleware import ResponsePolicyMiddleware


class ReadinessTests(TestCase):
    @override_settings(ALFABANK_PASSWORD="must-never-appear", CDEK_CLIENT_SECRET="also-private")
    def test_report_lists_missing_business_data_without_credentials_or_writes(self):
        out = StringIO()
        call_command("check_store_readiness", stdout=out)
        result = out.getvalue()
        self.assertIn("ИНН продавца", result)
        self.assertIn("Нет активного способа доставки СДЭК", result)
        self.assertNotIn("must-never-appear", result)
        self.assertNotIn("also-private", result)
        self.assertFalse(Product.objects.exists())
        with self.assertRaises(CommandError):
            call_command("check_store_readiness", strict=True, stdout=StringIO())

    def test_published_demos_and_missing_parcels_are_reported_separately(self):
        Product.objects.create(
            sku="DEMO-READY",
            name="Демо",
            slug="demo-ready",
            price="100",
            status="published",
            purchasable=True,
        )
        out = StringIO()
        call_command("check_store_readiness", stdout=out)
        self.assertIn("Опубликованы демо-товары", out.getvalue())
        self.assertIn("вес/размеры транспортной упаковки", out.getvalue())


class CheckoutMapPolicyTests(TestCase):
    @override_settings(ALFABANK_ENABLED=True, PAYMENT_STUB_ENABLED=False)
    def test_bank_form_action_matches_only_selected_environment_and_private_shop_pages(self):
        middleware = ResponsePolicyMiddleware(lambda request: HttpResponse())
        for test_mode, origin in ((True, "https://alfa.rbsuat.com"), (False, "https://pay.alfabank.ru")):
            with override_settings(ALFABANK_TEST_MODE=test_mode):
                for path, shop, allowed in (
                    ("/checkout/", True, True),
                    ("/orders/example/", True, True),
                    ("/", True, False),
                    ("/checkout/", False, False),
                ):
                    request = RequestFactory().get(path)
                    request.is_shop = shop
                    policy = middleware(request)["Content-Security-Policy"]
                    self.assertEqual(origin in policy, allowed)
                    self.assertEqual(policy.count(origin), int(allowed))
                    self.assertIn("script-src 'self';", policy)

    @override_settings(CDEK_ENABLED=True)
    def test_external_map_policy_is_limited_to_checkout_and_has_no_eval_or_card_post(self):
        middleware = ResponsePolicyMiddleware(lambda request: HttpResponse())
        for path, shop, allowed in (
            ("/checkout/", True, True),
            ("/", True, False),
            ("/admin/", True, False),
            ("/checkout/", False, False),
        ):
            request = RequestFactory().get(path)
            request.is_shop = shop
            policy = middleware(request)["Content-Security-Policy"]
            self.assertEqual("tile.openstreetmap.org" in policy, allowed)
            self.assertNotIn("cdn.jsdelivr.net", policy)
            self.assertNotIn("unsafe-eval", policy)
            self.assertIn("form-action 'self'", policy)

    @override_settings(CDEK_ENABLED=False)
    def test_disabled_integration_keeps_checkout_csp_local(self):
        request = RequestFactory().get("/checkout/")
        request.is_shop = True
        policy = ResponsePolicyMiddleware(lambda request: HttpResponse())(request)["Content-Security-Policy"]
        self.assertNotIn("yandex", policy)
        self.assertNotIn("jsdelivr", policy)
