"""Safety checks for the operator helper, always using a disposable test database."""

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.mail.backends.locmem import EmailBackend
from django.core.management import call_command
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings

from apps.catalog.models import Product
from apps.orders.models import DeliveryMethod, Notification, Order, StoreSettings
from deploy import check_unpaid_order as check


@override_settings(
    DEBUG=False,
    DEVELOPMENT=False,
    ALLOWED_HOSTS=["shop.localhost"],
    SHOP_HOST="shop.localhost",
    SHOP_ORIGIN="https://shop.localhost",
    CSRF_TRUSTED_ORIGINS=["https://shop.localhost"],
    CHECKOUT_ENABLED=True,
    ALFABANK_ENABLED=False,
    ALFABANK_TEST_MODE=True,
    ALFABANK_LIVE_APPROVED=False,
    PAYMENT_STUB_ENABLED=True,
    CDEK_ENABLED=True,
    CDEK_DEMO_QUOTES_ENABLED=True,
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="smtp.example.invalid",
    EMAIL_HOST_USER="tests-only",
    EMAIL_HOST_PASSWORD="tests-only",
    EMAIL_USE_TLS=True,
    EMAIL_USE_SSL=False,
    EMAIL_TIMEOUT=10,
    DEFAULT_FROM_EMAIL="store@example.test",
    MANAGER_EMAIL="manager@example.test",
    EMAIL_REPLY_TO="manager@example.test",
)
class UnpaidAcceptanceTests(TransactionTestCase):
    def setUp(self):
        StoreSettings.objects.update_or_create(
            pk=1,
            defaults={"checkout_enabled": True, "terms_text": "Тестовые условия", "privacy_text": "Политика"},
        )
        self.product = Product.objects.create(
            name="Проверочный товар",
            sku="DEMO-QA",
            slug="demo-qa",
            price="690.00",
            stock=5,
            purchasable=True,
            status="published",
        )
        DeliveryMethod.objects.create(
            name="СДЭК", slug="cdek", type="cdek_pvz", price="0.00", active=True, is_default=True
        )
        self.methods = list(DeliveryMethod.objects.order_by("pk").values())
        self.run_id = "acceptance-test"
        self.buyer = "buyer@example.test"

    def assert_delivery_unchanged(self):
        self.assertEqual(list(DeliveryMethod.objects.order_by("pk").values()), self.methods)
        self.assertTrue(settings.PAYMENT_STUB_ENABLED)
        self.assertTrue(settings.CDEK_ENABLED)
        self.assertTrue(settings.CDEK_DEMO_QUOTES_ENABLED)

    def test_create_mail_retry_and_cancel_use_normal_services(self):
        order_id, created = check.create_check(self.buyer, self.run_id)
        self.assertTrue(created)
        self.assertEqual(check.create_check(self.buyer, self.run_id), (order_id, False))
        self.assertEqual(Order.objects.count(), 1)
        self.assert_delivery_unchanged()
        order = Order.objects.get(pk=order_id)
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.reserved_stock), (5, 1))
        self.assertEqual(order.financial_status, "unpaid")
        self.assertEqual(
            set(order.notifications.values_list("recipient", flat=True)), {self.buyer, settings.MANAGER_EMAIL}
        )

        # A failed SMTP send preserves both notices; a later worker sends them once.
        with patch("django.core.mail.backends.smtp.EmailBackend", EmailBackend):
            with patch.object(EmailBackend, "send_messages", side_effect=OSError("simulated SMTP failure")):
                call_command("send_notifications", stdout=StringIO())
            self.assertEqual(order.notifications.filter(sent_at__isnull=True, attempts=1).count(), 2)
            from django.utils import timezone

            order.notifications.update(next_attempt_at=timezone.now())
            call_command("send_notifications", stdout=StringIO())
            self.assertEqual(len(mail.outbox), 2)
            self.assertTrue(all(message.subject.startswith("[ТЕСТ] Заказ создан") for message in mail.outbox))
            call_command("send_notifications", stdout=StringIO())
            self.assertEqual(len(mail.outbox), 2)
            check.cancel_check(self.run_id)
            check.cancel_check(self.run_id)
            call_command("send_notifications", stdout=StringIO())
            self.assertEqual(len(mail.outbox), 4)
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.reserved_stock), (5, 0))
        state = check.status_check(self.run_id)
        self.assertEqual((state["status"], state["payment"]), ("canceled", "unpaid"))
        self.assertTrue(all(notice["sent_at"] for notice in state["notifications"]))
        self.assert_delivery_unchanged()

    def test_failed_assertion_rolls_back_order_reserve_and_notifications(self):
        with patch.object(check, "check_access", side_effect=check.CheckFailed("simulated failure")):
            with self.assertRaisesRegex(check.CheckFailed, "simulated failure"):
                check.create_check(self.buyer, self.run_id)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Notification.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.reserved_stock), (5, 0))
        self.assert_delivery_unchanged()

    def test_bank_or_real_product_or_same_mailbox_are_rejected(self):
        with override_settings(ALFABANK_ENABLED=True):
            with self.assertRaises(check.CheckFailed):
                check.create_check(self.buyer, self.run_id)
        with self.assertRaisesRegex(check.CheckFailed, "separate customer mailbox"):
            check.create_check(settings.MANAGER_EMAIL, self.run_id)
        self.product.sku = "REAL-001"
        self.product.save(update_fields=["sku"])
        with self.assertRaisesRegex(check.CheckFailed, "No available DEMO"):
            check.create_check(self.buyer, self.run_id)
        self.assertFalse(Order.objects.exists())
        self.assert_delivery_unchanged()

    def test_existing_run_cannot_be_reassigned_or_unrelated_order_canceled(self):
        order_id, _ = check.create_check(self.buyer, self.run_id)
        with self.assertRaisesRegex(check.CheckFailed, "another mailbox"):
            check.create_check("another@example.test", self.run_id)
        Order.objects.filter(pk=order_id).update(comment="Unrelated order")
        with self.assertRaisesRegex(check.CheckFailed, "not owned"):
            check.cancel_check(self.run_id)
        self.assertEqual(Order.objects.get(pk=order_id).status, "new")
        self.assertEqual(Order.objects.count(), 1)

    @skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL transaction isolation")
    def test_public_connection_never_sees_temporary_delivery_method(self):
        actual_check_access = check.check_access

        def public_methods():
            try:
                return list(DeliveryMethod.objects.order_by("pk").values())
            finally:
                connections.close_all()

        def inspect_transaction(order, client):
            self.assertTrue(DeliveryMethod.objects.filter(slug__startswith="qa-").exists())
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertEqual(pool.submit(public_methods).result(timeout=10), self.methods)
            actual_check_access(order, client)

        with patch.object(check, "check_access", side_effect=inspect_transaction):
            check.create_check(self.buyer, self.run_id)
        self.assert_delivery_unchanged()
