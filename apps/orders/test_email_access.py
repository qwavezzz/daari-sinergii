import re
from unittest.mock import patch

from django.core import signing
from django.test import Client, TestCase, override_settings

from .access import SALT, make_access_token
from .models import Notification
from .notifications import build_notification_email
from .services import create_order
from .test_support import checkout_data, fixture_cart


class EmailAccessTests(TestCase):
    def setUp(self):
        cart, _, method = fixture_cart()
        self.order = create_order(cart, checkout_data(cart, method), cart.session_key)
        self.client = Client(HTTP_HOST="shop.localhost")

    def link(self, token=None, order=None):
        order = order or self.order
        return f"/orders/{order.public_id}/access/?token={token or make_access_token(order)}"

    def test_email_opens_only_its_order_on_another_device_and_cleans_url(self):
        notice = self.order.notifications.get(audience=Notification.Audience.CUSTOMER)
        email = build_notification_email(notice)
        url = re.search(r"https?://[^\s]+/access/\?token=[^\s]+", email.body).group(0)
        response = self.client.get(url)
        self.assertRedirects(response, self.order.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertIn("no-store", response["Cache-Control"])
        detail = self.client.get(self.order.get_absolute_url())
        self.assertContains(detail, self.order.name)
        self.assertEqual(detail["Referrer-Policy"], "same-origin")
        stranger = Client(HTTP_HOST="shop.localhost")
        self.assertEqual(stranger.get(self.order.get_absolute_url()).status_code, 404)
        cart, _, method = fixture_cart("another-owner")
        other = create_order(cart, checkout_data(cart, method), cart.session_key)
        self.assertEqual(self.client.get(other.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(self.link(make_access_token(self.order), other)).status_code, 410)

    @override_settings(ORDER_EMAIL_LINK_MAX_AGE=60)
    def test_expiry_is_checked_again_after_session_grant(self):
        with patch("django.core.signing.time.time", return_value=1000):
            token = make_access_token(self.order)
            self.assertEqual(self.client.get(self.link(token)).status_code, 302)
        with patch("django.core.signing.time.time", return_value=1061):
            self.assertEqual(self.client.get(self.link(token)).status_code, 410)
            self.assertEqual(self.client.get(self.order.get_absolute_url()).status_code, 404)

    def test_tampering_email_change_and_explicit_revocation_invalidate_access(self):
        token = make_access_token(self.order)
        for invalid in (token + "x", "x" * 600, signing.dumps([], salt=SALT)):
            response = self.client.get(self.link(invalid))
            self.assertEqual(response.status_code, 410)
            self.assertNotContains(response, self.order.email, status_code=410)
        self.client.get(self.link(token))
        self.order.access_version += 1
        self.order.save(update_fields=["access_version"])
        self.assertEqual(self.client.get(self.order.get_absolute_url()).status_code, 404)
        token = make_access_token(self.order)
        self.order.email = "changed@example.test"
        self.order.save(update_fields=["email"])
        self.assertEqual(self.client.get(self.link(token)).status_code, 410)
