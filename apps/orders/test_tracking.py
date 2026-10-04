from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase

from .services import create_order, set_tracking_number
from .test_support import checkout_data, fixture_cart


class TrackingTests(TestCase):
    def setUp(self):
        cart, _, method = fixture_cart()
        self.order = create_order(cart, checkout_data(cart, method), cart.session_key)

    def test_requires_verified_payment_and_retries_do_not_duplicate_mail(self):
        with self.assertRaises(ValidationError):
            set_tracking_number(self.order.pk, "123456789")
        self.order.financial_status = "paid"
        self.order.save()
        for invalid in ("", "x", "<script>alert(1)</script>", "A" * 81):
            with self.assertRaises(ValidationError):
                set_tracking_number(self.order.pk, invalid)
        set_tracking_number(self.order.pk, "123456789")
        set_tracking_number(self.order.pk, "123456789")
        self.assertEqual(self.order.notifications.filter(event__startswith="tracking-").count(), 2)
        set_tracking_number(self.order.pk, "987654321")
        call_command("send_notifications", stdout=StringIO())
        tracking = [m for m in mail.outbox if "Трек-номер" in m.subject and m.to == [self.order.email]]
        self.assertEqual(len(tracking), 2)
        self.assertIn("123456789", tracking[0].body)
        self.assertIn("987654321", tracking[1].body)

    def test_admin_action_requires_post_csrf_and_permission(self):
        user = get_user_model().objects.create_superuser("owner", password="fixture")
        client = Client(HTTP_HOST="shop.localhost", enforce_csrf_checks=True)
        client.force_login(user)
        url = f"/admin/orders/order/{self.order.pk}/tracking/"
        self.assertEqual(client.get(url).status_code, 405)
        self.assertEqual(client.post(url, {"tracking_number": "123456789"}).status_code, 403)
        client.get(f"/admin/orders/order/{self.order.pk}/change/")
        token = client.cookies["csrftoken"].value
        user.is_superuser = False
        user.save()
        self.assertEqual(
            client.post(url, {"tracking_number": "123456789", "csrfmiddlewaretoken": token}).status_code, 403
        )
