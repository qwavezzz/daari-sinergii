from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from .cdek import CdekClient, DeliveryUnavailable
from .test_cdek import CDEK_SETTINGS
from .test_support import fixture_cart


@override_settings(**CDEK_SETTINGS)
class MapDirectoryTests(TestCase):
    def setUp(self):
        cache.clear()
        session = self.client.session
        session.save()
        fixture_cart(session_key=session.session_key)

    def test_map_loads_country_directory_without_city_lookup_and_caches_pages(self):
        page = {"offices": [{"code": "TLT2", "latitude": 53.5, "longitude": 49.4}], "next_page": 1}
        with (
            patch.object(CdekClient, "map_points", return_value=page) as fetch,
            patch.object(CdekClient, "cities") as cities,
        ):
            for _ in range(2):
                response = self.client.get("/checkout/cdek/map-points/?page=0", HTTP_HOST="shop.localhost")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), page)
            fetch.assert_called_once_with(0)
            cities.assert_not_called()
        self.assertEqual(
            self.client.get("/checkout/cdek/map-points/?page=200", HTTP_HOST="shop.localhost").status_code,
            400,
        )

    def test_map_page_keeps_only_handout_pvz_in_russia_and_reports_pagination(self):
        row = {
            "code": "TLT2",
            "type": "PVZ",
            "is_handout": True,
            "work_time": "9-18",
            "location": {
                "country_code": "RU",
                "city_code": 431,
                "city": "Тольятти",
                "address": "Ленина, 44",
                "latitude": 53.5,
                "longitude": 49.4,
            },
        }

        def offices(filters, response_headers):
            self.assertEqual(filters, {"page": 0, "size": 500})
            response_headers["X-Total-Elements"] = "501"
            return [
                row,
                {**row, "type": "POSTAMAT"},
                {**row, "is_handout": False},
                {**row, "location": {**row["location"], "country_code": "KZ"}},
            ]

        with patch.object(CdekClient, "offices", side_effect=offices):
            result = CdekClient().map_points(0)
        self.assertEqual(len(result["offices"]), 1)
        self.assertEqual(result["offices"][0]["city"], "Тольятти")
        self.assertEqual(result["next_page"], 1)

    def test_http_client_does_not_send_connection_close_or_follow_redirects(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b"[]"
        response.headers = {"X-Total-Elements": "0"}
        with patch("apps.orders.cdek.HTTPSConnection") as factory:
            connection = factory.return_value
            connection.getresponse.return_value = response
            client = CdekClient()
            self.assertEqual(
                client._request("deliverypoints", params={"city_code": 431}, token="private-token"), []
            )
            request = connection.request.call_args
            self.assertEqual(request.args, ("GET", "/v2/deliverypoints?city_code=431"))
            self.assertNotIn("Connection", request.kwargs["headers"])
            connection.close.assert_called_once()
            response.status = 302
            with self.assertRaises(DeliveryUnavailable):
                client._request("deliverypoints", token="private-token")
            self.assertEqual(connection.request.call_count, 2)
            response.status = 200
            response.read.return_value = b"x" * 8_000_001
            with self.assertRaises(DeliveryUnavailable):
                client._request("deliverypoints")
