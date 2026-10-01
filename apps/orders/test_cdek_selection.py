from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from .cdek import CdekClient, DeliveryUnavailable
from .test_cdek import CDEK_SETTINGS
from .test_support import fixture_cart


@override_settings(**CDEK_SETTINGS)
class CdekSelectionTests(TestCase):
    def setUp(self):
        cache.clear()
        session = self.client.session
        session.save()
        self.cart, _, _ = fixture_cart(session_key=session.session_key)

    def get(self, endpoint, **params):
        return self.client.get(f"/checkout/cdek/{endpoint}/", params, HTTP_HOST="shop.localhost")

    def test_search_uses_official_city_contract_and_returns_only_display_fields(self):
        rows = [{"code": 123, "city": "Самара", "region": "Самарская область", "country_code": "RU"}]
        with (
            patch.object(CdekClient, "_token", return_value="secret"),
            patch.object(CdekClient, "_request", return_value=rows) as request,
        ):
            response = self.get("cities", q="Самара", url="https://evil.invalid", size="99999")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json()["cities"], [{"code": 123, "city": "Самара", "region": "Самарская область"}]
            )
            self.assertEqual(request.call_args.args, ("location/cities",))
            self.assertEqual(
                request.call_args.kwargs["params"],
                {"country_codes": "RU", "city": "Самара", "size": 21, "page": 0, "lang": "rus"},
            )
            self.assertNotIn("secret", response.content.decode())
            self.get("cities", q="Самара")
            self.assertEqual(request.call_count, 1)

    def test_invalid_queries_are_rejected_before_provider_io(self):
        with patch.object(CdekClient, "_request") as request:
            for query in ("", "а", "а" * 81, "Город\x00", "https://evil.invalid"):
                self.assertEqual(self.get("cities", q=query).status_code, 400)
            for city_code in ("", "-1", "NaN", "9" * 5000, "１２３"):
                self.assertEqual(self.get("offices", city_code=city_code).status_code, 400)
            self.assertEqual(self.get("offices", city_code="123", page="1000").status_code, 400)
            request.assert_not_called()

    def test_offices_are_filtered_paginated_and_do_not_publish_provider_payload(self):
        office = {
            "code": "TEST1",
            "type": "PVZ",
            "is_handout": True,
            "name": "Пункт",
            "work_time": "Пн–Пт 9–18",
            "internal": "hidden",
            "location": {"country_code": "RU", "city_code": 123, "city": "Самара", "address": "Мира, 1"},
        }

        def upstream(path, **kwargs):
            self.assertEqual(path, "deliverypoints")
            self.assertEqual(
                kwargs["params"],
                {
                    "country_code": "RU",
                    "type": "PVZ",
                    "is_handout": "true",
                    "city_code": 123,
                    "page": 0,
                    "size": 50,
                },
            )
            kwargs["response_headers"]["X-Total-Elements"] = "60"
            return [office, {**office, "code": "CLOSED", "is_handout": False}]

        with (
            patch.object(CdekClient, "_token", return_value="token"),
            patch.object(CdekClient, "_request", side_effect=upstream),
        ):
            response = self.get("offices", city_code="123")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["next_page"], 1)
        self.assertEqual([row["code"] for row in response.json()["offices"]], ["TEST1"])
        self.assertEqual(response.json()["offices"][0]["address"], "Мира, 1")
        self.assertNotIn("hidden", response.content.decode())

    def test_missing_credentials_fail_even_after_a_cached_search(self):
        with patch.object(CdekClient, "cities", return_value={"cities": [], "has_more": False}):
            self.assertEqual(self.get("cities", q="Москва").status_code, 200)
        with override_settings(CDEK_CLIENT_SECRET=""), patch.object(CdekClient, "_request") as request:
            response = self.get("cities", q="Москва")
            self.assertEqual(response.status_code, 503)
            self.assertIn("не подключён", response.json()["message"])
            request.assert_not_called()

    def test_provider_failure_can_be_retried_and_search_requires_active_cart(self):
        with patch.object(CdekClient, "cities", side_effect=DeliveryUnavailable("Повторите поиск.")):
            self.assertEqual(self.get("cities", q="Москва").status_code, 503)
        with patch.object(CdekClient, "cities", return_value={"cities": [], "has_more": False}):
            self.assertEqual(self.get("cities", q="Москва").status_code, 200)
        self.cart.items.all().delete()
        self.assertEqual(self.get("cities", q="Москва").status_code, 403)

    def test_search_is_rate_limited_before_provider_call(self):
        with (
            patch("apps.orders.views.allow_request", return_value=False),
            patch.object(CdekClient, "cities") as cities,
        ):
            self.assertEqual(self.get("cities", q="Москва").status_code, 429)
            cities.assert_not_called()

    def test_malformed_city_result_does_not_become_a_selectable_city(self):
        with (
            patch.object(CdekClient, "_token", return_value="token"),
            patch.object(
                CdekClient,
                "_request",
                return_value=[
                    None,
                    {"code": True, "city": "Город", "country_code": "RU"},
                    {"code": 123, "city": "Город", "country_code": "XX"},
                ],
            ),
        ):
            response = self.get("cities", q="Город")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cities"], [])
