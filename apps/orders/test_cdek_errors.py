import json
from http.client import HTTPException
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from .cdek import CdekClient, DeliveryUnavailable, TariffUnavailable
from .test_cdek import CDEK_SETTINGS


NO_TARIFF = {
    "errors": [
        {
            "code": "err_result_service_empty",
            "additional_code": "0xBC236B02",
            "message": "По данному направлению при заданных условиях выбранный тариф недоступен",
        }
    ]
}


@override_settings(**CDEK_SETTINGS)
class CdekHttpErrorTests(SimpleTestCase):
    def setUp(self):
        self.provider = CdekClient()
        self.factory_patch = patch("apps.orders.cdek.HTTPSConnection")
        self.factory = self.factory_patch.start()
        self.connection = self.factory.return_value
        self.addCleanup(self.factory_patch.stop)
        self.response = MagicMock()
        self.response.__enter__.return_value = self.response
        self.response.headers = {}
        self.connection.getresponse.return_value = self.response

    def response_body(self, status, data=None, *, raw=None):
        self.connection.reset_mock()
        self.response.reset_mock()
        self.response.status = status
        self.response.read.return_value = json.dumps(data).encode() if raw is None else raw

    def request_failure(self, *, path="calculator/tariff", exception=DeliveryUnavailable):
        with self.assertRaises(exception) as caught:
            self.provider._request(path, token="private-token", payload={"tariff_code": 136})
        self.connection.request.assert_called_once()
        self.connection.close.assert_called_once()
        return caught.exception

    def test_known_no_tariff_allows_another_plan_on_http_error_and_success_envelope(self):
        for status in (200, 400, 422):
            with self.subTest(status=status):
                self.response_body(status, NO_TARIFF)
                failure = self.request_failure(exception=TariffUnavailable)
                self.assertEqual(failure.code, "cdek_tariff_unavailable")
                self.assertEqual(failure.status_code, status)
                self.assertEqual(failure.provider_codes, ("err_result_service_empty", "0xBC236B02"))
                self.assertIn("Выберите другой пункт", str(failure))
                self.assertNotIn("не ответил", str(failure))
                self.response.read.assert_called_once_with(8_000_001 if status == 200 else 64_001)

    def test_sender_directory_failure_is_not_a_packing_rejection(self):
        self.response_body(400, {"errors": [{"code": "v2_sender_location_not_recognized"}]})
        failure = self.request_failure()
        self.assertNotIsInstance(failure, TariffUnavailable)
        self.assertEqual(failure.code, "cdek_sender_location")
        self.assertIn("менять пункт выдачи не нужно", str(failure))

    def test_http_auth_throttling_server_and_redirect_failures_never_try_more_plans(self):
        for status, code in (
            (401, "cdek_authentication"),
            (403, "cdek_authentication"),
            (429, "cdek_rate_limited"),
            (500, "cdek_service_unavailable"),
            (503, "cdek_service_unavailable"),
            (302, "cdek_request_rejected"),
        ):
            with self.subTest(status=status), patch("apps.orders.cdek.cache.delete") as clear:
                self.response_body(status, NO_TARIFF)
                failure = self.request_failure()
                self.assertNotIsInstance(failure, TariffUnavailable)
                self.assertEqual(failure.code, code)
                if status in (401, 403):
                    clear.assert_called_once_with(self.provider.token_key)
                else:
                    clear.assert_not_called()

    def test_only_unambiguous_known_calculator_errors_allow_alternative_packing(self):
        unknown = {"code": "validation_error", "message": NO_TARIFF["errors"][0]["message"]}
        for errors in (
            [unknown],
            [{"additional_code": "0xBC236B02"}],
            [NO_TARIFF["errors"][0], unknown],
            [NO_TARIFF["errors"][0], "malformed"],
            {"code": "err_result_service_empty"},
            "err_result_service_empty",
            True,
        ):
            with self.subTest(errors=errors):
                self.response_body(400, {"errors": errors})
                failure = self.request_failure()
                self.assertNotIsInstance(failure, TariffUnavailable)
                self.assertEqual(failure.code, "cdek_request_rejected")
        self.response_body(400, NO_TARIFF)
        failure = self.request_failure(path="deliverypoints")
        self.assertNotIsInstance(failure, TariffUnavailable)
        self.response_body(200, {**NO_TARIFF, "error": "invalid_client"})
        failure = self.request_failure()
        self.assertNotIsInstance(failure, TariffUnavailable)

    def test_oauth_invalid_client_is_configuration_failure_without_leaking_free_text(self):
        self.response_body(
            400,
            {"error": "invalid_client", "error_description": "private-token test-secret secret credentials"},
        )
        with patch("apps.orders.cdek.cache.delete") as clear:
            failure = self.request_failure(path="oauth/token")
        self.assertEqual(failure.code, "cdek_authentication")
        self.assertEqual(failure.provider_codes, ("invalid_client",))
        self.assertIn("менеджеру", str(failure))
        self.assertNotIn("secret", str(failure))
        clear.assert_called_once_with(self.provider.token_key)

    def test_error_diagnostics_are_bounded_and_exclude_provider_messages(self):
        self.response_body(
            400,
            {
                "errors": [
                    {"code": "validation_error", "additional_code": "0xABC", "message": "private-token"},
                    {"code": "<script>test-secret</script>", "additional_code": "x" * 65},
                    {"code": "validation_error"},
                ]
            },
        )
        failure = self.request_failure()
        self.assertEqual(failure.provider_codes, ("validation_error", "0xABC"))
        self.assertNotIn("private-token", str(failure))
        self.assertNotIn("test-secret", str(failure))

    def test_malformed_error_bodies_preserve_status_classification(self):
        for status, code in (
            (400, "cdek_request_rejected"),
            (401, "cdek_authentication"),
            (429, "cdek_rate_limited"),
            (502, "cdek_service_unavailable"),
        ):
            for raw in (b"", b"<html>private-token</html>", b"\xff", b"null", b"[]", b"x" * 64_001):
                with self.subTest(status=status, length=len(raw)), patch("apps.orders.cdek.cache.delete"):
                    self.response_body(status, raw=raw)
                    failure = self.request_failure()
                    self.assertNotIsInstance(failure, TariffUnavailable)
                    self.assertEqual(failure.code, code)
                    self.assertEqual(failure.provider_codes, ())
                    self.assertNotIn("private-token", str(failure))
                    self.response.read.assert_called_once_with(64_001)

    def test_malformed_success_is_protocol_failure_and_never_a_new_plan_request(self):
        for raw in (
            b"",
            b"<html>private-token</html>",
            b"\xff",
            b"null",
            b"123",
            b"true",
            b"x" * 8_000_001,
        ):
            with self.subTest(length=len(raw)):
                self.response_body(200, raw=raw)
                failure = self.request_failure()
                self.assertNotIsInstance(failure, TariffUnavailable)
                self.assertEqual(failure.code, "cdek_invalid_response")
                self.assertNotIn("private-token", str(failure))
                self.response.read.assert_called_once_with(8_000_001)

    def test_transport_failures_are_not_retried_and_connection_is_closed(self):
        for error, code in (
            (TimeoutError("private-token"), "cdek_timeout"),
            (OSError("private-token"), "cdek_connection_failed"),
            (HTTPException("private-token"), "cdek_connection_failed"),
        ):
            with self.subTest(error=type(error).__name__):
                self.connection.reset_mock()
                self.connection.getresponse.side_effect = error
                failure = self.request_failure()
                self.assertNotIsInstance(failure, TariffUnavailable)
                self.assertEqual(failure.code, code)
                self.assertNotIn("private-token", str(failure))

    def test_success_keeps_payload_pagination_and_empty_error_list_protocol(self):
        for result in ([], {"total_sum": 125, "period_min": 1, "period_max": 3, "errors": []}):
            with self.subTest(result=result):
                self.response_body(200, result)
                self.response.headers = {"X-Total-Elements": "123"}
                headers = {}
                actual = self.provider._request(
                    "calculator/tariff",
                    token="private-token",
                    payload={"tariff_code": 136},
                    response_headers=headers,
                )
                self.assertEqual(actual, result)
                self.assertEqual(headers, {"X-Total-Elements": "123"})
                self.connection.request.assert_called_once()
                self.connection.close.assert_called_once()
                call = self.connection.request.call_args
                self.assertEqual(call.args, ("POST", "/v2/calculator/tariff"))
                self.assertEqual(json.loads(call.kwargs["body"]), {"tariff_code": 136})
                self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer private-token")

    @override_settings(CDEK_TIMEOUT_SECONDS=9)
    def test_no_deadline_keeps_configured_timeout_and_does_not_read_clock(self):
        self.response_body(200, [])
        with patch("apps.orders.cdek.monotonic") as clock:
            self.assertEqual(self.provider._request("deliverypoints"), [])
        self.factory.assert_called_once_with("api.edu.cdek.ru", timeout=9)
        clock.assert_not_called()

    def test_exhausted_budget_does_not_open_connection_for_any_endpoint(self):
        for path in ("oauth/token", "deliverypoints", "calculator/tariff"):
            for current in (100, 100.5):
                with (
                    self.subTest(path=path, current=current),
                    patch("apps.orders.cdek.monotonic", return_value=current),
                ):
                    self.provider.deadline = 100
                    with self.assertRaises(DeliveryUnavailable) as caught:
                        self.provider._request(path, payload={})
                    self.assertEqual(caught.exception.code, "comparison_timeout")
                    self.assertNotIsInstance(caught.exception, TariffUnavailable)
                    self.assertIn("Повторите расчёт", str(caught.exception))
                    self.factory.assert_not_called()
                    self.connection.request.assert_not_called()

    @override_settings(CDEK_TIMEOUT_SECONDS=9)
    def test_auth_and_office_requests_share_budget_and_next_calculation_cannot_overrun_it(self):
        self.provider = CdekClient(deadline=120)
        self.response_body(200, [])
        self.response.read.side_effect = [
            b'{"access_token": "new-token", "expires_in": 3600}',
            b"[]",
        ]
        with (
            patch("apps.orders.cdek.cache.get", return_value=None),
            patch("apps.orders.cdek.cache.set"),
            patch("apps.orders.cdek.monotonic", side_effect=[100, 117.5, 120]),
        ):
            self.assertEqual(self.provider.offices(), [])
            with self.assertRaises(DeliveryUnavailable) as caught:
                self.provider._request("calculator/tariff", token="new-token", payload={})
        self.assertEqual(caught.exception.code, "comparison_timeout")
        self.assertEqual(self.factory.call_count, 2)
        self.assertEqual([call.kwargs["timeout"] for call in self.factory.call_args_list], [9, 2.5])
        self.assertEqual(self.connection.request.call_count, 2)
        self.assertEqual(self.connection.close.call_count, 2)
