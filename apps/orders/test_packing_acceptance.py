"""The operator rehearsal must preserve the public catalogue and reject unsafe runs."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from io import StringIO
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.core.mail.backends.locmem import EmailBackend
from django.core.management import call_command
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings

from apps.catalog.models import Product
from apps.orders.cdek import CdekClient, DeliveryUnavailable
from apps.orders.models import DeliveryMethod, Notification, Order, PackingBox, StoreSettings
from deploy import check_packing_order as check
from deploy.check_unpaid_order import CheckFailed


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
    CDEK_TEST_MODE=False,
    CDEK_DEMO_QUOTES_ENABLED=False,
    CDEK_FROM_CITY_CODE=431,
    CDEK_FROM_PVZ_CODE="TLT4",
    CDEK_CLIENT_ID="packing-acceptance-only",
    CDEK_CLIENT_SECRET="packing-acceptance-only",
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
class PackingAcceptanceTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        StoreSettings.objects.update_or_create(
            pk=1,
            defaults={
                "checkout_enabled": True,
                "terms_text": "Тестовые условия",
                "privacy_text": "Политика",
            },
        )
        call_command("setup_auto_packing", "--with-demo", stdout=StringIO())
        DeliveryMethod.objects.create(
            name="СДЭК",
            slug="cdek",
            type="cdek_pvz",
            active=True,
            is_default=True,
            cdek_tariff_code=136,
            price=0,
        )
        self.sources = list(Product.objects.order_by("pk").values())
        self.boxes = list(PackingBox.objects.order_by("pk").values())
        self.methods = list(DeliveryMethod.objects.order_by("pk").values())
        self.buyer, self.run_id = "buyer@example.test", "packing-test"
        self.payloads = []
        self.reject_pickup = False
        self.api_failure = False

        def transport(client, path, **kwargs):
            self.assertEqual(client.base, "https://api.cdek.ru/v2")
            if path == "oauth/token":
                return {"access_token": "acceptance-token", "expires_in": 3600}
            if path == "deliverypoints":
                code = kwargs["params"]["code"]
                self.assertIn(code, ("MSK2", "TLT4"))
                return [
                    {
                        "code": code,
                        "type": "PVZ",
                        "is_handout": not self.reject_pickup,
                        "is_reception": True,
                        "status": "ACTIVE",
                        "location": {
                            "country_code": "RU",
                            "city_code": 431 if code == "TLT4" else 44,
                            "city": "Тольятти" if code == "TLT4" else "Москва",
                            "address": "Свердлова, 13а" if code == "TLT4" else "Международная, 15",
                        },
                    }
                ]
            self.assertEqual(path, "calculator/tariff")
            if self.api_failure:
                raise DeliveryUnavailable("Simulated API failure")
            payload = kwargs["payload"]
            self.payloads.append(payload)
            self.assertEqual(payload["delivery_point"], "MSK2")
            self.assertEqual(payload["shipment_point"], "TLT4")
            self.assertEqual(payload["tariff_code"], 136)
            self.assertEqual(payload["services"], [{"code": "INSURANCE", "parameter": 2580.0}])
            # Make the larger shared box cheaper: the real pricing loop must choose it.
            price = "600.00" if payload["packages"][0]["length"] == 22 else "475.01"
            return {"total_sum": price, "period_min": 2, "period_max": 2, "currency": "RUB"}

        boundary = patch.object(CdekClient, "_request", transport)
        boundary.start()
        self.addCleanup(boundary.stop)

    def assert_public_unchanged(self):
        self.assertEqual(
            list(Product.objects.filter(sku__in=check.SOURCE_SKUS).order_by("pk").values()), self.sources
        )
        self.assertEqual(list(PackingBox.objects.order_by("pk").values()), self.boxes)
        self.assertEqual(list(DeliveryMethod.objects.order_by("pk").values()), self.methods)
        self.assertFalse(Product.objects.filter(status="published").exists())
        self.assertTrue(settings.PAYMENT_STUB_ENABLED)
        self.assertFalse(settings.CDEK_TEST_MODE)

    def test_order_uses_selected_pvz_cheapest_shared_box_email_and_cancel(self):
        pk, created = check.create_check(self.buyer, self.run_id)
        self.assertTrue(created)
        order = Order.objects.get(pk=pk)
        self.assertEqual(check.create_check(self.buyer, self.run_id), (pk, False))
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(len(self.payloads), 2)
        self.assertEqual(order.delivery_snapshot["packing"]["parcels"][0]["box_code"], "demo-auto-large")
        self.assertEqual(order.address, "Москва, Международная, 15")
        self.assertEqual(order.delivery_price, Decimal("525.01"))
        self.assertEqual(order.total, Decimal("3105.01"))
        self.assertEqual(order.reservations.filter(state="active").count(), 2)
        self.assert_public_unchanged()
        with patch("django.core.mail.backends.smtp.EmailBackend", EmailBackend):
            call_command("send_notifications", stdout=StringIO())
            self.assertEqual(len(mail.outbox), 2)
            self.assertEqual({m.to[0] for m in mail.outbox}, {self.buyer, settings.MANAGER_EMAIL})
            self.assertTrue(all(m.subject.startswith("[ТЕСТ] Заказ создан") for m in mail.outbox))
            self.assertTrue(all("MSK2" in m.body and "Международная" in m.body for m in mail.outbox))
        check.cancel_check(self.run_id)
        check.cancel_check(self.run_id)
        state = check.status_check(self.run_id)
        self.assertEqual((state["status"], state["payment"]), ("canceled", "unpaid"))
        self.assertEqual(order.reservations.filter(state="released").count(), 2)
        self.assertFalse(Product.objects.filter(reserved_stock__gt=0).exists())
        self.assert_public_unchanged()

    def test_failure_after_checkout_rolls_back_order_products_and_mail(self):
        with patch.object(check, "check_access", side_effect=CheckFailed("forced failure")):
            with self.assertRaisesRegex(CheckFailed, "forced failure"):
                check.create_check(self.buyer, self.run_id)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(Product.objects.count(), 2)
        self.assert_public_unchanged()

    def test_api_failure_or_unavailable_pvz_does_not_leave_order(self):
        for flag in ("api_failure", "reject_pickup"):
            with self.subTest(flag=flag):
                setattr(self, flag, True)
                with self.assertRaisesRegex(CheckFailed, "CDEK quote failed"):
                    check.create_check(self.buyer, self.run_id)
                setattr(self, flag, False)
                self.assertFalse(Order.objects.exists())
                self.assertFalse(Notification.objects.exists())
                self.assertEqual(Product.objects.count(), 2)
                self.assert_public_unchanged()

    def test_enabled_bank_or_sandbox_or_other_sender_block_creation(self):
        for change in ({"ALFABANK_ENABLED": True}, {"CDEK_TEST_MODE": True}, {"CDEK_FROM_PVZ_CODE": "TLT3"}):
            with self.subTest(change=change), override_settings(**change), self.assertRaises(CheckFailed):
                check.create_check(self.buyer, self.run_id)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(Product.objects.count(), 2)

    def test_existing_run_cannot_change_recipient_or_cancel_other_order(self):
        pk, _ = check.create_check(self.buyer, self.run_id)
        with self.assertRaisesRegex(CheckFailed, "another mailbox"):
            check.create_check("other@example.test", self.run_id)
        Order.objects.filter(pk=pk).update(comment="Unrelated order")
        with self.assertRaisesRegex(CheckFailed, "not owned"):
            check.cancel_check(self.run_id)
        self.assertEqual(Order.objects.get(pk=pk).status, "new")

    @skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL visibility checks")
    def test_other_connection_never_sees_published_qa_products(self):
        original_access = check.check_access

        def public_products():
            try:
                return list(Product.objects.filter(status="published").values_list("pk", flat=True))
            finally:
                connections.close_all()

        def inspect(order, client):
            self.assertEqual(Product.objects.filter(status="published").count(), 2)
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertEqual(pool.submit(public_products).result(timeout=10), [])
            original_access(order, client)

        with patch.object(check, "check_access", side_effect=inspect):
            check.create_check(self.buyer, self.run_id)
        self.assert_public_unchanged()
