import json
from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.management.commands.check_store_operations import operation_report
from apps.core.models import AuditEntry, WorkerHeartbeat
from apps.core.operations import worker_finished
from apps.orders.services import create_order
from apps.orders.test_support import checkout_data, fixture_cart


class OperationsTests(TestCase):
    def test_fresh_workers_then_stale_workers(self):
        self.assertFalse(operation_report()["healthy"])
        worker_finished("notifications")
        worker_finished("payments")
        self.assertTrue(operation_report()["healthy"])
        WorkerHeartbeat.objects.filter(name="payments").update(
            finished_at=timezone.now() - timedelta(hours=1)
        )
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("check_store_operations", strict=True, json=True, stdout=out)
        self.assertIn("worker.payments.stale", json.loads(out.getvalue())["issues"])

    def test_old_mail_skipped_duplicates_and_shipping_errors(self):
        worker_finished("notifications")
        worker_finished("payments", failures=1)
        cart, _, method = fixture_cart()
        order = create_order(cart, checkout_data(cart, method), cart.session_key)
        order.notifications.update(created_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(operation_report()["metrics"]["mail_overdue"], 2)
        order.notifications.update(skipped_at=timezone.now())
        self.assertEqual(operation_report()["metrics"]["mail_overdue"], 0)
        for _ in range(3):
            AuditEntry.objects.create(kind="cdek.quote_failed", object_id="", message="DeliveryUnavailable")
        self.assertIn("shipping_failures_15m", operation_report()["issues"])

    @override_settings(OPERATIONS_EMAIL="operator@example.test")
    def test_alert_is_explicit_and_rate_limited_without_customer_data(self):
        call_command("check_store_operations", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)
        call_command("check_store_operations", notify=True, stdout=StringIO())
        call_command("check_store_operations", notify=True, stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["operator@example.test"])

    def test_configuration_check_does_not_fake_worker_success(self):
        call_command("send_notifications", check=True, stdout=StringIO())
        self.assertFalse(WorkerHeartbeat.objects.exists())
        call_command("send_notifications", stdout=StringIO())
        self.assertTrue(WorkerHeartbeat.objects.filter(name="notifications").exists())
