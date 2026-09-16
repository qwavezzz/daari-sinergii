from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from orders.models import Notification, NotificationSettings, StockReservation
from orders.notifications import build_notification_email
from orders.services import create_order, queue_notification, transition_order
from orders.test_support import checkout_data, fixture_cart


class NotificationTests(TestCase):
    def setUp(self):
        cart, self.product, method = fixture_cart()
        self.order = create_order(
            cart,
            checkout_data(cart, method, comment='<script>alert("x")</script>'),
            cart.session_key,
        )

    def send(self, **options):
        call_command("send_notifications", stdout=StringIO(), **options)

    def test_buyer_and_manager_receive_distinct_complete_multipart_messages(self):
        self.product.name = "Новое имя каталога"
        self.product.price = 999
        self.product.save()
        self.send()
        self.assertEqual(len(mail.outbox), 2)
        buyer = next(m for m in mail.outbox if m.to == [self.order.email])
        manager = next(m for m in mail.outbox if m.to == ["manager@example.test"])
        for message in mail.outbox:
            self.assertIn("Тестовый товар", message.body)
            self.assertNotIn("Новое имя каталога", message.body)
            self.assertIn("Стоимость заказа: 150 ₽", message.body)
            self.assertIn("Получение: 50 ₽", message.body)
            self.assertEqual(message.alternatives[0].mimetype, "text/html")
            self.assertNotIn('<script>alert("x")</script>', message.alternatives[0].content)
            self.assertIn("&lt;script&gt;", message.alternatives[0].content)
            self.assertNotIn(self.order.session_key, message.body)
        self.assertIn(self.order.get_absolute_url(), buyer.body)
        self.assertNotIn("/admin/", buyer.body)
        self.assertIn(f"/admin/orders/order/{self.order.pk}/change/", manager.body)
        self.assertNotIn(self.order.get_absolute_url(), manager.body)
        self.send()
        self.assertEqual(len(mail.outbox), 2)

    def test_admin_address_overrides_env_and_retargets_only_unsent_manager_mail(self):
        # Customer mail must still go to the buyer, even after a manager address change.
        self.send(limit=1)
        NotificationSettings.objects.update_or_create(
            pk=1,
            defaults={"manager_email": "replacement@example.test", "reply_to_email": "help@example.test"},
        )
        self.send()
        self.assertEqual([m.to for m in mail.outbox], [[self.order.email], ["replacement@example.test"]])
        self.assertEqual(mail.outbox[-1].reply_to, ["help@example.test"])
        manager = Notification.objects.get(audience="manager")
        self.assertEqual(manager.recipient, "replacement@example.test")
        self.assertIsNotNone(manager.sent_at)
        NotificationSettings.objects.filter(pk=1).update(manager_email="third@example.test")
        self.send()
        self.assertEqual(len(mail.outbox), 2)

    def test_rerouting_to_already_notified_address_does_not_send_duplicate(self):
        self.send(limit=1)
        NotificationSettings.objects.filter(pk=1).update(manager_email=self.order.email)
        self.send()
        self.assertEqual(len(mail.outbox), 1)
        notice = Notification.objects.get(audience="manager")
        self.assertIsNone(notice.sent_at)
        self.assertIsNotNone(notice.skipped_at)

    @override_settings(MANAGER_EMAIL="buyer@example.test")
    def test_new_events_with_shared_buyer_manager_address_have_one_customer_message(self):
        Notification.objects.all().delete()
        queue_notification(self.order, "processing")
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(Notification.objects.get().audience, "customer")

    def test_smtp_failure_retries_later_without_starving_new_mail_or_changing_message_id(self):
        notice = Notification.objects.get(audience="customer")
        message_id = build_notification_email(notice).extra_headers["Message-ID"]
        with patch("orders.notifications.EmailMultiAlternatives.send", side_effect=OSError("private-error")):
            self.send()
        notice.refresh_from_db()
        self.assertIsNone(notice.sent_at)
        self.assertEqual(notice.attempts, 1)
        self.assertEqual(notice.last_error, "OSError")
        self.assertGreater(notice.next_attempt_at, timezone.now() + timedelta(seconds=50))
        self.send()
        notice.refresh_from_db()
        self.assertEqual(notice.attempts, 1)
        queue_notification(self.order, "processing")
        self.send(limit=1)
        self.assertIn("Заказ в обработке", mail.outbox[0].subject)
        Notification.objects.filter(event="created").update(
            next_attempt_at=timezone.now() - timedelta(seconds=1)
        )
        self.send()
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(
            next(
                m for m in mail.outbox if "Заказ создан" in m.subject and m.to == [self.order.email]
            ).extra_headers["Message-ID"],
            message_id,
        )
        notice.refresh_from_db()
        self.assertEqual(notice.attempts, 2)
        self.assertEqual(notice.last_error, "")

    def test_backend_returning_zero_is_not_marked_sent(self):
        with patch("orders.notifications.EmailMultiAlternatives.send", return_value=0):
            self.send()
        self.assertFalse(Notification.objects.filter(sent_at__isnull=False).exists())

    def test_check_is_read_only_and_invalid_transport_keeps_queue_untouched(self):
        self.send(check=True)
        self.assertEqual(len(mail.outbox), 0)
        with override_settings(DEFAULT_FROM_EMAIL=""), self.assertRaises(CommandError):
            self.send()
        with override_settings(MANAGER_EMAIL=""), self.assertRaises(CommandError):
            self.send()
        with override_settings(DEVELOPMENT=False), self.assertRaises(CommandError):
            self.send()
        with (
            override_settings(
                EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                EMAIL_HOST="smtp.example.test",
                EMAIL_USE_SSL=True,
                EMAIL_USE_TLS=True,
            ),
            self.assertRaises(CommandError),
        ):
            self.send()
        self.assertFalse(Notification.objects.filter(attempts__gt=0).exists())

    def test_expired_unpaid_reservation_queues_one_cancellation_event(self):
        StockReservation.objects.filter(order=self.order).update(
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        call_command("reconcile_payments", stdout=StringIO())
        call_command("reconcile_payments", stdout=StringIO())
        self.assertEqual(Notification.objects.filter(event="canceled").count(), 2)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "canceled")

    def test_status_notifications_are_atomic_idempotent_and_guarded(self):
        transition_order(self.order.pk, "processing")
        transition_order(self.order.pk, "processing")
        self.assertEqual(Notification.objects.filter(event="processing").count(), 2)
        with self.assertRaises(ValidationError):
            transition_order(self.order.pk, "ready")
        self.assertFalse(Notification.objects.filter(event="ready").exists())
        with self.assertRaises(RuntimeError), transaction.atomic():
            transition_order(self.order.pk, "canceled")
            raise RuntimeError("rollback")
        self.assertFalse(Notification.objects.filter(event="canceled").exists())
        transition_order(self.order.pk, "canceled")
        self.assertEqual(Notification.objects.filter(event="canceled").count(), 2)

    def test_paid_fulfillment_sends_ready_and_completed_events(self):
        self.order.financial_status = "paid"
        self.order.save(update_fields=["financial_status"])
        for state in ("processing", "ready", "completed"):
            transition_order(self.order.pk, state)
        self.assertEqual(Notification.objects.filter(event__in=["ready", "completed"]).count(), 4)

    def test_manager_can_change_addresses_but_editor_and_public_cannot(self):
        call_command("setup_roles", stdout=StringIO())
        manager = User.objects.create_user("mail-manager", is_staff=True)
        manager.groups.add(Group.objects.get(name="Менеджер магазина"))
        url = "/admin/orders/notificationsettings/1/change/"
        self.client.force_login(manager)
        Notification.objects.update(next_attempt_at=timezone.now() + timedelta(hours=1))
        response = self.client.post(
            url,
            {
                "manager_email": "replacement@example.test",
                "reply_to_email": "help@example.test",
                "_save": "1",
            },
            HTTP_HOST="shop.localhost",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(NotificationSettings.objects.get(pk=1).manager_email, "replacement@example.test")
        self.assertLessEqual(Notification.objects.get(audience="manager").next_attempt_at, timezone.now())
        self.assertGreater(Notification.objects.get(audience="customer").next_attempt_at, timezone.now())
        self.assertFalse(manager.has_perm("orders.change_storesettings"))
        editor = User.objects.create_user("mail-editor", is_staff=True)
        editor.groups.add(Group.objects.get(name="Контент-редактор"))
        self.client.force_login(editor)
        self.assertEqual(self.client.get(url, HTTP_HOST="shop.localhost").status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url, HTTP_HOST="shop.localhost").status_code, 302)
