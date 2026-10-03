from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from .cdek import CdekClient
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
            points = CdekClient().map_points(0)["offices"]
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
