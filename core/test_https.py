"""Verify browser-facing HSTS behavior with the production environment settings."""

import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.http import HttpResponse
from django.middleware.security import SecurityMiddleware
from django.test import RequestFactory, SimpleTestCase, override_settings


class HstsPolicyTests(SimpleTestCase):
    def response(self, *, seconds="300", include=None, secure=True, host="dari-sinergii.ru"):
        with patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "config.settings_test"}):
            os.environ["HSTS_SECONDS"] = seconds
            os.environ.pop("HSTS_INCLUDE_SUBDOMAINS", None)
            if include is not None:
                os.environ["HSTS_INCLUDE_SUBDOMAINS"] = include
            values = runpy.run_path(str(Path(__file__).resolve().parents[1] / "config" / "settings.py"))
        policy = {key: value for key, value in values.items() if key.startswith("SECURE_")}
        with override_settings(**policy, ALLOWED_HOSTS=[host]):
            request = RequestFactory().get(
                "/", HTTP_HOST=host, HTTP_X_FORWARDED_PROTO="https" if secure else "http"
            )
            return SecurityMiddleware(lambda request: HttpResponse("ok"))(request)

    def test_disabled_policy_has_no_header(self):
        self.assertNotIn("Strict-Transport-Security", self.response(seconds="0"))

    def test_short_policy_applies_to_each_served_host_without_subdomains(self):
        for host in ("dari-sinergii.ru", "shop.dari-sinergii.ru"):
            with self.subTest(host=host):
                response = self.response(host=host)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Strict-Transport-Security"], "max-age=300")

    def test_subdomains_require_explicit_environment_opt_in(self):
        self.assertEqual(self.response(include="false")["Strict-Transport-Security"], "max-age=300")
        self.assertEqual(
            self.response(include="true")["Strict-Transport-Security"],
            "max-age=300; includeSubDomains",
        )

    def test_plain_http_redirects_without_an_hsts_header(self):
        response = self.response(secure=False)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://dari-sinergii.ru/")
        self.assertNotIn("Strict-Transport-Security", response)
