import os
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase
from django.test import RequestFactory

import manage
from config.local_environment import load_local_environment
from .http import navigation_redirect


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
                    "YOOKASSA_SECRET_KEY": "environment-fixture",
                },
                clear=True,
            ),
            patch("config.local_environment.Path.is_file", return_value=True),
            patch(
                "config.local_environment.Path.read_text",
                return_value='{"YOOKASSA_SECRET_KEY":"file-fixture","YOOKASSA_TEST_MODE":true}',
            ),
        ):
            load_local_environment()
            self.assertEqual(os.environ["YOOKASSA_SECRET_KEY"], "environment-fixture")
            self.assertEqual(os.environ["YOOKASSA_TEST_MODE"], "true")


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
