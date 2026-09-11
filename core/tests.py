from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase
from django.test import RequestFactory
from .http import navigation_redirect


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
