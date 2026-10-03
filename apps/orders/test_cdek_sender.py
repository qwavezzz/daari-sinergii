from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from .cdek import CdekClient, DeliveryUnavailable, TariffUnavailable
from .services import QuoteChanged, create_order
from .shipping import quote_delivery, verified_delivery
from .test_cdek import CDEK_SETTINGS, PICKUP
from .test_support import checkout_data, fixture_cart


SENDER_SETTINGS = {**CDEK_SETTINGS, "CDEK_FROM_CITY_CODE": 431, "CDEK_FROM_PVZ_CODE": "TLT3"}
SENDER = {
    "code": "TLT3",
    "city_code": 431,
    "city": "Тольятти",
    "address": "ул. 70 лет Октября, 31а, 105",
    "weight_min_g": "0",
    "weight_max_g": "30000",
}
OFFICE = {
    "code": "TLT3",
    "type": "PVZ",
    "status": "ACTIVE",
    "is_reception": True,
    # A sender need not offer collection; the directory request must not filter it out.
    "is_handout": False,
    "weight_max": 30,
    "location": {
        "city_code": 431,
        "country_code": "RU",
        "city": SENDER["city"],
        "address": SENDER["address"],
    },
}


@override_settings(**SENDER_SETTINGS)
class CdekSenderBoundaryTests(TestCase):
    def test_calculator_sends_validated_origin_address_and_both_point_codes(self):
        client = CdekClient()

        def upstream(path, **kwargs):
            if path == "deliverypoints":
                self.assertEqual(kwargs["params"]["code"], "TLT3")
                self.assertEqual(kwargs["params"]["is_reception"], "true")
                self.assertNotIn("is_handout", kwargs["params"])
                return [OFFICE]
            self.assertEqual(path, "calculator/tariff")
            return {"total_sum": 321.40, "period_min": 2, "period_max": 5}

        with (
            patch.object(client, "_token", return_value="test-token"),
            patch.object(client, "_request", side_effect=upstream) as request,
        ):
            for weight in (400, 800):
                result = client.calculate(
                    136,
                    PICKUP,
                    [{"weight": weight, "length": 20, "width": 10, "height": 10}],
                    declared_value=Decimal("200.00"),
                )
                self.assertEqual(result["price"], "321.40")
                payload = request.call_args.kwargs["payload"]
                self.assertEqual(payload["shipment_point"], "TLT3")
                self.assertEqual(payload["delivery_point"], "TEST1")
                self.assertEqual(
                    payload["from_location"],
                    {"code": 431, "country_code": "RU", "city": SENDER["city"], "address": SENDER["address"]},
                )
                self.assertEqual(payload["services"], [{"code": "INSURANCE", "parameter": 200.0}])
        self.assertEqual(sum(call.args == ("deliverypoints",) for call in request.call_args_list), 1)

    def test_invalid_origin_is_never_sent_to_calculator(self):
        for office in (
            {**OFFICE, "is_reception": False},
            {**OFFICE, "status": "CLOSED"},
            {**OFFICE, "code": "TLT2"},
            {**OFFICE, "location": {**OFFICE["location"], "city_code": 44}},
        ):
            with self.subTest(office=office):
                client = CdekClient()
                with (
                    patch.object(client, "offices", return_value=[office]),
                    patch.object(client, "_request") as request,
                    self.assertRaises(DeliveryUnavailable),
                ):
                    client.calculate(136, PICKUP, [{"weight": 400}])
                request.assert_not_called()

    def test_origin_weight_limit_checked_before_calculator(self):
        client = CdekClient()
        with (
            patch.object(client, "shipment_point", return_value={**SENDER, "weight_max_g": "300"}),
            patch.object(client, "_request") as request,
            self.assertRaises(TariffUnavailable),
        ):
            client.calculate(136, PICKUP, [{"weight": 400}])
        request.assert_not_called()

    def test_without_explicit_origin_city_and_recipient_still_sent(self):
        with override_settings(CDEK_FROM_PVZ_CODE=""):
            client = CdekClient()
            with (
                patch.object(client, "_token", return_value="test-token"),
                patch.object(
                    client, "_request", return_value={"total_sum": 321, "period_min": 1, "period_max": 2}
                ) as request,
            ):
                client.calculate(136, PICKUP, [{"weight": 400}])
            self.assertEqual(request.call_args.kwargs["payload"]["from_location"], {"code": 431})
            self.assertNotIn("shipment_point", request.call_args.kwargs["payload"])
            self.assertEqual(request.call_args.kwargs["payload"]["delivery_point"], "TEST1")


@override_settings(**SENDER_SETTINGS)
class CdekSenderCheckoutTests(TestCase):
    def setUp(self):
        self.cart, self.product, self.method = fixture_cart(quantity=2)
        self.method.type = "cdek_pvz"
        self.method.cdek_tariff_code = 136
        self.method.save()
        self.product.package_weight_g = 450
        self.product.package_length_cm = 20
        self.product.package_width_cm = 10
        self.product.package_height_cm = 8
        self.product.save()
        self.product.confirm_package_measurements()
        self.provider = Mock()
        self.provider.pickup.return_value = dict(PICKUP)
        self.provider.shipment_point.return_value = dict(SENDER)
        self.provider.calculate.return_value = {"price": "321.40", "period_min": 2, "period_max": 5}
        boundary = patch("apps.orders.shipping.CdekClient", return_value=self.provider)
        boundary.start()
        self.addCleanup(boundary.stop)

    def quote(self):
        return quote_delivery(self.cart, self.method, "TEST1", self.cart.session_key)

    def test_sender_is_signed_saved_and_cannot_be_replaced_by_browser(self):
        result = self.quote()
        self.assertEqual(result["shipping"]["sender"], SENDER)
        data = checkout_data(
            self.cart,
            self.method,
            quote_token=result["quote_token"],
            delivery_quote=result["delivery_quote"],
            pvz_code="TEST1",
            shipment_point="WRONG",
        )
        order = create_order(self.cart, data, self.cart.session_key)
        self.assertEqual(order.delivery_snapshot["sender"], SENDER)

    def test_switching_origin_invalidates_quote(self):
        result = self.quote()
        for code in ("TLT2", ""):
            with (
                self.subTest(code=code),
                override_settings(CDEK_FROM_PVZ_CODE=code),
                self.assertRaises(QuoteChanged),
            ):
                verified_delivery(self.cart, self.method, result["delivery_quote"], "TEST1")

    def test_origin_weight_limit_filters_plans_before_calculating(self):
        self.provider.shipment_point.return_value = {**SENDER, "weight_max_g": "400"}
        with self.assertRaises(DeliveryUnavailable):
            self.quote()
        self.provider.calculate.assert_not_called()

    def test_reception_and_handout_limits_apply_to_each_parcel(self):
        self.provider.shipment_point.return_value = {**SENDER, "weight_max_g": "450"}
        self.provider.pickup.return_value = {**PICKUP, "weight_min_g": "450", "weight_max_g": "500"}
        result = self.quote()
        self.assertEqual(len(result["shipping"]["packages"]), 2)
        self.provider.calculate.assert_called_once()

    def test_diagnostic_command_shows_actual_sender_even_when_demo_mode_enabled(self):
        output = StringIO()
        with (
            override_settings(CDEK_DEMO_QUOTES_ENABLED=True),
            patch(
                "apps.orders.management.commands.check_cdek_connection.CdekClient", return_value=self.provider
            ),
        ):
            call_command("check_cdek_connection", pvz="TEST1", stdout=output)
        self.assertIn("TLT3", output.getvalue())
        self.assertIn(SENDER["address"], output.getvalue())
        self.assertIn("321.40", output.getvalue())
        self.provider.calculate.assert_called_once()
