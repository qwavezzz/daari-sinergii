import json
from io import BytesIO, StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.payments.provider import InvalidPayment, YooKassaClient
from apps.payments.services import reconcile_attempt, start_payment
from .models import StoreSettings
from .notifications import build_notification
from .services import create_order, queue_notification
from .test_support import checkout_data, fixture_cart


@override_settings(
    YOOKASSA_ENABLED=True,
    YOOKASSA_TEST_MODE=True,
    YOOKASSA_SHOP_ID="12345",
    YOOKASSA_SECRET_KEY="test-fixture-key",
)
class NotificationFlowTests(TestCase):
    def setUp(self):
        cart, self.product, method = fixture_cart()
        StoreSettings.objects.filter(pk=1).update(manager_email="sales@example.test")
        self.order = create_order(cart, checkout_data(cart, method), cart.session_key)

    def payment(self, status="pending"):
        return {
            "id": "fixture-payment-1",
            "status": status,
            "paid": status == "succeeded",
            "amount": {"value": str(self.order.total), "currency": "RUB"},
            "metadata": {"order_id": str(self.order.public_id)},
            "recipient": {"account_id": "12345"},
            "test": True,
            "confirmation": {"confirmation_url": "https://yoomoney.ru/checkout/fixture"},
        }

    def test_api_boundary_creates_and_confirms_test_payment_then_sends_four_role_specific_emails(self):
        calls = []

        def api(request, timeout):
            calls.append((request.method, request.full_url))
            if request.full_url.endswith("/me"):
                result = {"account_id": "12345", "test": True}
            elif request.method == "POST":
                self.assertIn("Idempotence-key", request.headers)
                self.assertEqual(json.loads(request.data)["amount"]["value"], "150.00")
                result = self.payment()
            else:
                result = self.payment("succeeded")
            return BytesIO(json.dumps(result).encode())

        with patch("apps.payments.provider.urlopen", side_effect=api):
            attempt = start_payment(self.order.pk)
            # Refund enumeration is separate from this payment/notification scenario.
            with patch.object(YooKassaClient, "list_refunds", return_value=[]):
                reconcile_attempt(attempt.pk)
                reconcile_attempt(attempt.pk)
        self.assertEqual(calls[0], ("GET", "https://api.yookassa.ru/v3/me"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.financial_status, "paid")
        self.assertEqual(self.order.notifications.count(), 4)
        call_command("send_notifications", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 4)
        customer = [message for message in mail.outbox if message.to == [self.order.email]]
        manager = [message for message in mail.outbox if message.to == ["sales@example.test"]]
        self.assertEqual(len(customer), 2)
        self.assertEqual(len(manager), 2)
        self.assertTrue(any("ожидает сборки" in message.subject for message in manager))
        for message in customer:
            self.assertNotIn("/admin/", message.body)
            self.assertEqual(message.alternatives[0].mimetype, "text/html")
        for message in manager:
            self.assertIn(f"/admin/orders/order/{self.order.pk}/change/", message.body)
        call_command("send_notifications", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 4)

    def test_wrong_shop_or_live_credentials_are_rejected_before_payment_creation(self):
        for data in ({"account_id": "12345", "test": False}, {"account_id": "other", "test": True}):
            with (
                self.subTest(data=data),
                patch.object(YooKassaClient, "request", return_value=data) as request,
            ):
                with self.assertRaises(InvalidPayment):
                    YooKassaClient().create_payment({}, "fixture-key")
                request.assert_called_once_with("GET", "me")

    def test_changing_manager_affects_new_events_and_same_email_retains_both_roles(self):
        StoreSettings.objects.filter(pk=1).update(manager_email=self.order.email)
        queue_notification(self.order, "paid")
        queue_notification(self.order, "paid")
        notices = self.order.notifications.filter(event="paid")
        self.assertEqual(notices.count(), 2)
        self.assertEqual(set(notices.values_list("audience", flat=True)), {"customer", "manager"})
        self.assertTrue(
            self.order.notifications.filter(event="created", recipient="sales@example.test").exists()
        )

    def test_failed_send_stays_queued_and_retry_preserves_message_id(self):
        notice = self.order.notifications.get(audience="manager")
        message_id = build_notification(notice).extra_headers["Message-ID"]
        with patch(
            "apps.orders.notifications.EmailMultiAlternatives.send", side_effect=OSError("private detail")
        ):
            call_command("send_notifications", stdout=StringIO())
        notice.refresh_from_db()
        self.assertIsNone(notice.sent_at)
        self.assertEqual(notice.last_error, "OSError")
        call_command("send_notifications", stdout=StringIO())
        notice.refresh_from_db()
        self.assertIsNotNone(notice.sent_at)
        self.assertEqual(build_notification(notice).extra_headers["Message-ID"], message_id)

    def test_attention_or_refund_does_not_request_assembly_and_html_is_escaped(self):
        self.order.name = "<script>unsafe</script>"
        self.order.needs_attention = True
        self.order.financial_status = "paid"
        self.order.save()
        queue_notification(self.order, "paid")
        notice = self.order.notifications.get(event="paid", audience="manager")
        message = build_notification(notice)
        self.assertNotIn("ожидает сборки", message.subject)
        self.assertNotIn("Начать сборку", message.body)
        self.assertNotIn("<script>", message.alternatives[0].content)
        self.assertIn("&lt;script&gt;", message.alternatives[0].content)


class BusinessAdminTests(TestCase):
    def setUp(self):
        call_command("setup_roles", stdout=StringIO())
        self.owner = get_user_model().objects.create_user(
            "owner-fixture", is_staff=True, password="fixture-password"
        )
        self.owner.groups.add(Group.objects.get(name="Владелец магазина"))
        cart, _, method = fixture_cart()
        self.order = create_order(cart, checkout_data(cart, method), cart.session_key)
        self.client = Client(HTTP_HOST="shop.localhost", enforce_csrf_checks=True)
        self.client.force_login(self.owner)

    def test_owner_dashboard_settings_and_permissions(self):
        response = self.client.get("/admin/")
        self.assertContains(response, "Ожидают сборки")
        self.assertContains(response, "Настройки магазина")
        self.assertNotContains(response, "/admin/auth/user/")
        self.assertEqual(self.client.get("/admin/auth/user/").status_code, 403)
        url = reverse("admin:orders_storesettings_change", args=[1], urlconf="config.shop_urls")
        self.client.get(url)
        response = self.client.post(
            url,
            {
                "manager_email": "new-manager@example.test",
                "checkout_enabled": "on",
                "terms_text": "Тестовые условия",
                "privacy_text": "Тестовая политика",
                "delivery_text": "",
                "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StoreSettings.objects.get().manager_email, "new-manager@example.test")

    def test_workflow_requires_post_csrf_permissions_and_verified_payment(self):
        self.order.financial_status = "paid"
        self.order.save()
        url = f"/admin/orders/order/{self.order.pk}/workflow/"
        response = self.client.get(f"/admin/orders/order/{self.order.pk}/change/")
        self.assertContains(response, "Начать сборку")
        self.assertNotContains(response, "paid_attempt_id")
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {"target": "processing"}).status_code, 403)
        token = self.client.cookies["csrftoken"].value
        response = self.client.post(url, {"target": "processing", "csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "processing")
        self.order.financial_status = "unpaid"
        self.order.save()
        self.client.post(url, {"target": "ready", "csrfmiddlewaretoken": token})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "processing")

    def test_editor_dashboard_does_not_leak_sales_or_manager_address(self):
        editor = get_user_model().objects.create_user("editor-fixture", is_staff=True)
        editor.groups.add(Group.objects.get(name="Контент-редактор"))
        self.client.force_login(editor)
        response = self.client.get("/admin/")
        self.assertContains(response, "Управление сайтом")
        self.assertNotContains(response, self.order.name)
        self.assertNotContains(response, "Ожидают сборки")
