from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from .cdek import CdekClient, DeliveryUnavailable
from .map_config import map_config
from .test_cdek import CDEK_SETTINGS
from .test_support import fixture_cart


@override_settings(**CDEK_SETTINGS)
class OsmPickupTests(TestCase):
    def setUp(self):
        cache.clear()
        session = self.client.session
        session.save()
        fixture_cart(session_key=session.session_key)

    def locate(self, **data):
        return self.client.post("/checkout/cdek/locate/", data, HTTP_HOST="shop.localhost")

    def test_coordinates_use_post_and_city_precision_without_persisting_location(self):
        city = {"city": {"code": 431, "city": "Тольятти", "region": "Самарская область"}}
        with patch.object(CdekClient, "city_at", return_value=city) as lookup:
            response = self.locate(latitude="53.5078123", longitude="49.4204123")
        self.assertEqual(response.status_code, 200)
        lookup.assert_called_once_with(53.51, 49.42)
        self.assertEqual(response.json(), city)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotIn("latitude", self.client.session)
        self.assertNotIn("longitude", self.client.session)
        self.assertEqual(
            self.client.get("/checkout/cdek/locate/", HTTP_HOST="shop.localhost").status_code, 405
        )
        csrf_client = Client(enforce_csrf_checks=True)
        self.assertEqual(
            csrf_client.post("/checkout/cdek/locate/", HTTP_HOST="shop.localhost").status_code, 403
        )

    def test_invalid_coordinates_fail_before_provider_requests(self):
        with patch.object(CdekClient, "city_at") as lookup:
            for latitude, longitude in [
                ("NaN", "1"),
                ("Infinity", "1"),
                ("91", "1"),
                ("1", "181"),
                ("", "1"),
                ("1", "x"),
            ]:
                with self.subTest(latitude=latitude, longitude=longitude):
                    self.assertEqual(self.locate(latitude=latitude, longitude=longitude).status_code, 400)
            lookup.assert_not_called()

    def test_location_rejects_foreign_city_and_malformed_api_response(self):
        client = CdekClient()
        with patch.object(client, "_token", return_value="private-token"):
            with patch.object(
                client,
                "_request",
                side_effect=[
                    {"code": 431, "city": "Тольятти"},
                    [{"code": 431, "city": "Тольятти", "country_code": "RU", "region": "Самарская область"}],
                ],
            ) as request:
                result = client.city_at(53.51, 49.42)
                self.assertEqual(result["city"]["code"], 431)
                self.assertEqual(request.call_args_list[0].args, ("location/coordinates",))
                self.assertEqual(
                    request.call_args_list[0].kwargs["params"], {"latitude": 53.51, "longitude": 49.42}
                )
                self.assertEqual(request.call_args_list[1].kwargs["params"]["country_codes"], "RU")
            for rows in ([], [{"code": 431, "country_code": "KZ"}], [{"code": 432, "country_code": "RU"}]):
                with (
                    patch.object(client, "_request", side_effect=[{"code": 431, "city": "Город"}, rows]),
                    self.assertRaises(DeliveryUnavailable),
                ):
                    client.city_at(53, 49)
            with (
                patch.object(client, "_request", return_value={"code": True, "city": "Город"}),
                self.assertRaises(DeliveryUnavailable),
            ):
                client.city_at(53, 49)

    def test_bad_point_coordinates_stay_in_list_but_cannot_be_plotted(self):
        base = {
            "type": "PVZ",
            "is_handout": True,
            "location": {"city_code": 431, "country_code": "RU", "address": "Адрес"},
        }
        rows = []
        for index, coords in enumerate([(53.5, 49.4), (None, None), ("NaN", 49), (91, 49), (True, 49)]):
            rows.append(
                {
                    **base,
                    "code": f"TEST{index}",
                    "location": {**base["location"], "latitude": coords[0], "longitude": coords[1]},
                }
            )
        with patch.object(CdekClient, "offices", return_value=rows):
            points = CdekClient().office_choices(431, 0)["offices"]
        self.assertEqual(len(points), 5)
        self.assertEqual(points[0]["latitude"], 53.5)
        for point in points[1:]:
            self.assertIsNone(point["latitude"])
            self.assertIsNone(point["longitude"])

    def test_map_policy_allows_only_tiles_and_checkout_geolocation(self):
        response = self.client.get("/checkout/", HTTP_HOST="shop.localhost")
        policy = response["Content-Security-Policy"]
        self.assertIn("script-src 'self';", policy)
        self.assertIn("https://tile.openstreetmap.org", policy)
        self.assertNotIn("yandex", policy)
        self.assertNotIn("jsdelivr", policy)
        self.assertIn("geolocation=(self)", response["Permissions-Policy"])
        self.assertEqual(response["Referrer-Policy"], "strict-origin-when-cross-origin")
        response = self.client.get("/", HTTP_HOST="shop.localhost")
        self.assertIn("geolocation=()", response["Permissions-Policy"])
        self.assertNotIn("tile.openstreetmap.org", response["Content-Security-Policy"])

    def test_tile_provider_configuration_cannot_inject_csp_sources(self):
        for url in (
            "http://example.test/{z}/{x}/{y}",
            "https://example.test/{z}/{x}/{y}; script-src *",
            "https://user:password@example.test/{z}/{x}/{y}",
            "https://{s}.example.test/{z}/{x}/{y}",
            "https://example.test:bad/{z}/{x}/{y}",
        ):
            with self.subTest(url=url), override_settings(CDEK_MAP_TILE_URL=url):
                self.assertEqual(map_config(), {})
        with override_settings(CDEK_MAP_TILE_URL="https://tiles.example.test/{z}/{x}/{y}.png"):
            self.assertEqual(map_config()["origin"], "https://tiles.example.test")
