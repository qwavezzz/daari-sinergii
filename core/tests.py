from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.test import RequestFactory
from .http import navigation_redirect
from .ratelimit import allow_request, client_address


class HostAndRoleTests(TestCase):
    def test_htmx_redirect_preserves_in_domain_navigation(self):
        request = RequestFactory().post("/", HTTP_HX_REQUEST="true")
        internal = navigation_redirect(request, "/orders/example/")
        external = navigation_redirect(request, "https://yookassa.ru/checkout/test")
        self.assertIn("HX-Location", internal.headers)
        self.assertNotIn("HX-Redirect", internal.headers)
        self.assertEqual(external["HX-Redirect"], "https://yookassa.ru/checkout/test")

    def test_unknown_host_is_rejected_and_admin_only_on_shop(self):
        self.assertEqual(self.client.get("/health/", HTTP_HOST="evil.example").status_code, 400)
        self.assertEqual(self.client.get("/admin/", HTTP_HOST="localhost").status_code, 404)
        self.assertEqual(self.client.get("/admin/", HTTP_HOST="shop.localhost").status_code, 302)

    def test_host_only_cookies_and_safe_response_policies(self):
        response = self.client.get("/cart/", HTTP_HOST="shop.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        self.assertIn("HX-History-Restore-Request", response["Vary"])

    def test_editor_has_no_order_or_payment_access(self):
        call_command("setup_roles", verbosity=0)
        editor = Group.objects.get(name="Контент-редактор")
        self.assertFalse(
            editor.permissions.filter(content_type__app_label__in=["orders", "payments", "auth"]).exists()
        )
        self.assertTrue(editor.permissions.filter(codename="publish_document").exists())
        manager = Group.objects.get(name="Менеджер магазина")
        self.assertTrue(manager.permissions.filter(codename="change_order").exists())
        self.assertFalse(
            manager.permissions.filter(codename__in=["change_paymentattempt", "delete_order"]).exists()
        )

    def test_login_rate_limit_cannot_be_reset_by_new_session_cookie(self):
        for _ in range(5):
            response = Client(HTTP_HOST="shop.localhost").post(
                "/admin/login/", {"username": "nonexistent", "password": "incorrect"}
            )
            self.assertEqual(response.status_code, 200)
        response = Client(HTTP_HOST="shop.localhost").post(
            "/admin/login/", {"username": "nonexistent", "password": "incorrect"}
        )
        self.assertEqual(response.status_code, 429)
        self.assertIn("Content-Security-Policy", response)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")

    def test_unix_proxy_does_not_share_login_bucket_between_visitors(self):
        factory = RequestFactory()
        first = factory.post("/admin/login/", REMOTE_ADDR="", HTTP_X_REAL_IP="192.0.2.1")
        second = factory.post("/admin/login/", REMOTE_ADDR="", HTTP_X_REAL_IP="192.0.2.2")
        for _ in range(5):
            self.assertTrue(allow_request(first, "admin-login", 5))
        self.assertFalse(allow_request(first, "admin-login", 5))
        self.assertTrue(allow_request(second, "admin-login", 5))

    def test_tcp_client_cannot_spoof_ip_with_forwarded_headers(self):
        request = RequestFactory().get(
            "/", REMOTE_ADDR="192.0.2.1", HTTP_X_REAL_IP="192.0.2.2", HTTP_X_FORWARDED_FOR="192.0.2.3"
        )
        self.assertEqual(client_address(request), "192.0.2.1")
        request.META["REMOTE_ADDR"] = ""
        request.META["HTTP_X_REAL_IP"] = "192.0.2.2, 192.0.2.3"
        self.assertEqual(client_address(request), "")


class IndexingTests(TestCase):
    def setUp(self):
        from catalog.models import Product

        self.product = Product.objects.create(
            name="Published", slug="published", sku="REAL-1", status="published"
        )

    def test_main_public_pages_indexable_while_shop_closed_in_headers_html_and_sitemap(self):
        main = self.client.get("/", HTTP_HOST="localhost")
        self.assertNotIn("X-Robots-Tag", main)
        self.assertNotContains(main, 'name="robots"')
        for path in ("/", "/products/published/", "/legal/privacy/"):
            response = self.client.get(path, HTTP_HOST="shop.localhost")
            self.assertContains(response, 'name="robots" content="noindex, nofollow"')
            self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
            partial = self.client.get(path, HTTP_HOST="shop.localhost", HTTP_HX_REQUEST="true")
            self.assertContains(partial, 'data-noindex="true"')
        self.assertNotContains(self.client.get("/sitemap.xml", HTTP_HOST="shop.localhost"), "<loc>")
        self.assertNotContains(self.client.get("/robots.txt", HTTP_HOST="shop.localhost"), "Sitemap:")
        self.assertNotContains(self.client.get("/robots.txt", HTTP_HOST="shop.localhost"), "Disallow: /\n")
        self.assertContains(self.client.get("/sitemap.xml", HTTP_HOST="localhost"), "<loc>")

    @override_settings(SHOP_INDEXING_ENABLED=True)
    def test_shop_gate_and_demo_detection_stay_consistent(self):
        self.assertNotIn("X-Robots-Tag", self.client.get("/", HTTP_HOST="shop.localhost"))
        self.assertContains(
            self.client.get("/sitemap.xml", HTTP_HOST="shop.localhost"), "/products/published/"
        )
        self.product.sku = "DEMO-1"
        self.product.save()
        self.assertEqual(
            self.client.get("/", HTTP_HOST="shop.localhost")["X-Robots-Tag"], "noindex, nofollow"
        )
        self.assertNotContains(self.client.get("/sitemap.xml", HTTP_HOST="shop.localhost"), "<loc>")

    @override_settings(SITE_INDEXING_ENABLED=False, SHOP_INDEXING_ENABLED=True)
    def test_staging_gate_applies_to_main_and_shop(self):
        for host in ("localhost", "shop.localhost"):
            self.assertEqual(self.client.get("/", HTTP_HOST=host)["X-Robots-Tag"], "noindex, nofollow")
            self.assertNotContains(self.client.get("/sitemap.xml", HTTP_HOST=host), "<loc>")

    def test_catalog_canonical_preserves_page_and_category_drops_tracking(self):
        from catalog.models import Category, Product

        category = Category.objects.create(name="Масла", slug="oils")
        self.product.categories.add(category)
        for number in range(12):
            product = Product.objects.create(
                name=f"Product {number}", slug=f"p-{number}", sku=f"REAL-{number + 2}", status="published"
            )
            product.categories.add(category)
        response = self.client.get("/?category=oils&page=2&utm_source=test", HTTP_HOST="shop.localhost")
        self.assertContains(response, 'href="http://shop.localhost:8000/?category=oils&amp;page=2"')
        self.assertContains(response, "Масла — Дары Синергии — страница 2")
