import os
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.test import RequestFactory

import manage
from config.local_environment import load_local_environment
from .http import navigation_redirect
from .ratelimit import allow_request, client_address


class ManageLauncherTests(SimpleTestCase):
    def test_local_commands_share_settings_and_respect_explicit_environment(self):
        scenarios = [
            ("runserver", {}, "config.settings_dev"),
            ("createsuperuser", {}, "config.settings_dev"),
            ("changepassword", {}, "config.settings_dev"),
            ("check", {}, "config.settings_dev"),
            ("migrate", {}, "config.settings_dev"),
            ("shell", {}, "config.settings_dev"),
            ("runserver", {"DJANGO_SETTINGS_MODULE": "config.settings"}, "config.settings"),
            ("createsuperuser", {"DJANGO_SETTINGS_MODULE": "config.settings"}, "config.settings"),
            ("migrate", {"DJANGO_SETTINGS_MODULE": "config.settings"}, "config.settings"),
            ("runserver", {"DJANGO_SETTINGS_MODULE": "config.settings_test"}, "config.settings_test"),
        ]
        for command, environment, expected in scenarios:
            with (
                self.subTest(command=command, environment=environment),
                patch.dict(os.environ, environment, clear=True),
                patch.object(manage.sys, "prefix", "active-environment"),
                patch.object(manage.sys, "base_prefix", "system-python"),
                patch.object(manage.sys, "argv", ["manage.py", command]),
                patch("django.core.management.execute_from_command_line") as execute,
                patch("manage.subprocess.run") as subprocess_run,
            ):
                manage.main()
                self.assertEqual(os.environ["DJANGO_SETTINGS_MODULE"], expected)
                execute.assert_called_once_with(["manage.py", command])
                subprocess_run.assert_not_called()

    def test_system_python_uses_project_environment_and_preserves_arguments_and_exit_code(self):
        arguments = ["runserver", "8002", "--settings=config.settings_test"]
        with (
            patch.object(manage.sys, "prefix", "system-python"),
            patch.object(manage.sys, "base_prefix", "system-python"),
            patch.object(manage.sys, "argv", ["manage.py", *arguments]),
            patch.object(Path, "is_file", return_value=True),
            patch("manage.subprocess.run", return_value=Mock(returncode=23)) as subprocess_run,
            self.assertRaises(SystemExit) as result,
        ):
            manage.main()
        root = Path(manage.__file__).resolve().parent
        python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess_run.assert_called_once_with([str(python), str(root / "manage.py"), *arguments])
        self.assertEqual(result.exception.code, 23)


class LocalIntegrationSettingsTests(SimpleTestCase):
    def test_private_file_is_ignored_in_production_and_tests(self):
        for module in ("config.settings", "config.settings_test"):
            with (
                patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": module}, clear=True),
                patch("config.local_environment.Path.is_file") as exists,
            ):
                load_local_environment()
                exists.assert_not_called()

    def test_explicit_environment_wins_over_local_credentials(self):
        with (
            patch.dict(
                os.environ,
                {
                    "DJANGO_SETTINGS_MODULE": "config.settings_dev",
                    "ALFABANK_PASSWORD": "environment-fixture",
                },
                clear=True,
            ),
            patch("config.local_environment.Path.is_file", return_value=True),
            patch(
                "config.local_environment.Path.read_text",
                return_value='{"ALFABANK_PASSWORD":"file-fixture","ALFABANK_TEST_MODE":true}',
            ),
        ):
            load_local_environment()
            self.assertEqual(os.environ["ALFABANK_PASSWORD"], "environment-fixture")
            self.assertEqual(os.environ["ALFABANK_TEST_MODE"], "true")


class HostAndRoleTests(TestCase):
    def test_authenticated_admin_sections_are_available_on_shop_host(self):
        user = get_user_model().objects.create_superuser("admin-test", password="test-only-password")
        self.client.force_login(user)
        for path in (
            "/admin/",
            "/admin/content/document/",
            "/admin/catalog/product/",
            "/admin/orders/order/",
            "/admin/payments/paymentattempt/",
            "/admin/auth/user/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path, HTTP_HOST="shop.localhost")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Дары Синергии")

    def test_htmx_redirect_preserves_in_domain_navigation(self):
        request = RequestFactory().post("/", HTTP_HX_REQUEST="true")
        internal = navigation_redirect(request, "/orders/example/")
        external = navigation_redirect(request, "https://alfa.rbsuat.com/payment/merchants/test/payment.html")
        self.assertIn("HX-Location", internal.headers)
        self.assertNotIn("HX-Redirect", internal.headers)
        self.assertEqual(
            external["HX-Redirect"], "https://alfa.rbsuat.com/payment/merchants/test/payment.html"
        )

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
        from apps.catalog.models import Product

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
        from apps.catalog.models import Category, Product

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
