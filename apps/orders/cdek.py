"""CDEK API v2 boundary. Credentials and arbitrary upstream URLs never reach the widget."""

import hashlib
import json
import math
import re
from http.client import HTTPSConnection, HTTPException
from decimal import Decimal, DecimalException, InvalidOperation
from time import monotonic
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError


class DeliveryUnavailable(ValidationError):
    pass


class TariffUnavailable(DeliveryUnavailable):
    """The carrier rejected this packing plan; another plan may be quotable."""


def _provider_failure(path, status, result):
    """Classify a bounded response without exposing the carrier's arbitrary text."""
    errors = result.get("errors") if isinstance(result, dict) else None
    rows = errors if isinstance(errors, list) else []
    codes = []
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        for key in ("code", "additional_code"):
            value = row.get(key)
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", value):
                codes.append(value)
    oauth_code = result.get("error") if isinstance(result, dict) else None
    if isinstance(oauth_code, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", oauth_code):
        codes.append(oauth_code)

    exception = DeliveryUnavailable
    if status == 429:
        code = "cdek_rate_limited"
        message = "СДЭК временно ограничил число запросов. Повторите расчёт через минуту."
    elif status >= 500:
        code = "cdek_service_unavailable"
        message = "Сервис СДЭК временно недоступен. Повторите расчёт позже — товары сохранены."
    elif status in (401, 403) or path == "oauth/token":
        code = "cdek_authentication"
        message = "Магазину не удалось подключиться к СДЭК. Сообщите об этом менеджеру — товары сохранены."
    elif (
        path == "calculator/tariff"
        and (200 <= status < 300 or status in (400, 422))
        and not oauth_code
        and rows
        and all(isinstance(row, dict) and row.get("code") == "err_result_service_empty" for row in rows)
    ):
        # A recorded CDEK no-tariff response. Do not infer retryability from
        # translated messages, arbitrary 400s, or errors from other endpoints.
        exception = TariffUnavailable
        code = "cdek_tariff_unavailable"
        message = (
            "Выбранный тариф СДЭК недоступен для этих посылок и направления. "
            "Выберите другой пункт выдачи или обратитесь в магазин."
        )
    else:
        code = "cdek_request_rejected"
        message = "СДЭК отклонил параметры доставки. Обратитесь в магазин для проверки расчёта."
    failure = exception(message, code=code)
    failure.status_code = status
    failure.provider_codes = tuple(dict.fromkeys(codes))
    return failure


def configured():
    return bool(
        getattr(settings, "CDEK_ENABLED", False)
        and getattr(settings, "CDEK_CLIENT_ID", "")
        and getattr(settings, "CDEK_CLIENT_SECRET", "")
        and getattr(settings, "CDEK_FROM_CITY_CODE", 0) > 0
    )


def safe_code(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", value):
        raise DeliveryUnavailable("Проверьте код пункта СДЭК и повторите расчёт.")
    return value.upper()


def _weight_limits(minimum, maximum, *, unit=1):
    """Normalize optional CDEK limits; zero maximum means no upper bound."""
    try:
        limits = [Decimal(str(value if value is not None else 0)) * unit for value in (minimum, maximum)]
        if any(not value.is_finite() or value < 0 for value in limits):
            raise ValueError("weight restriction")
        if limits[1] and limits[0] > limits[1]:
            raise ValueError("reversed weight restriction")
    except (DecimalException, TypeError, ValueError) as exc:
        raise DeliveryUnavailable("Не удалось проверить ограничения пункта. Выберите другой пункт.") from exc
    return limits


def coordinates(latitude, longitude):
    """Return finite WGS84 coordinates; missing values must never become (0, 0)."""
    try:
        if isinstance(latitude, bool) or isinstance(longitude, bool):
            raise ValueError
        latitude, longitude = float(latitude), float(longitude)
        if not (math.isfinite(latitude) and math.isfinite(longitude)):
            raise ValueError
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError
    except (ValueError, TypeError, OverflowError) as exc:
        raise DeliveryUnavailable("Не удалось определить местоположение. Введите город вручную.") from exc
    return latitude, longitude


class CdekClient:
    def __init__(self, *, deadline=None):
        if not configured():
            raise DeliveryUnavailable("Расчёт СДЭК пока не подключён. Товары сохранятся в корзине.")
        self.deadline = deadline
        self.base = "https://api.edu.cdek.ru/v2" if settings.CDEK_TEST_MODE else "https://api.cdek.ru/v2"
        identity = f"{self.base}:{settings.CDEK_CLIENT_ID}:{settings.CDEK_CLIENT_SECRET}"
        self.token_key = "cdek-oauth:" + hashlib.sha256(identity.encode()).hexdigest()

    def _request(self, path, *, params=None, payload=None, token=None, form=None, response_headers=None):
        url = self.base + "/" + path
        if params:
            url += "?" + urlencode(params)
        headers = {
            "Accept": "application/json",
            "X-App-Name": "dari-sinergii",
            "User-Agent": "dari-sinergii/1.0",
        }
        body = None
        if token:
            headers["Authorization"] = "Bearer " + token
        if form is not None:
            body = urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        endpoint = urlsplit(url)
        timeout = getattr(settings, "CDEK_TIMEOUT_SECONDS", 10)
        if self.deadline is not None:
            remaining = self.deadline - monotonic()
            if remaining <= 0:
                raise DeliveryUnavailable(
                    "СДЭК не успел рассчитать варианты доставки. Повторите расчёт через минуту — товары сохранены.",
                    code="comparison_timeout",
                )
            # This limits each socket operation, not the total duration of a
            # response (DNS and successive reads can outlast the remaining budget).
            timeout = min(timeout, remaining)
        connection = HTTPSConnection(endpoint.hostname, timeout=timeout)
        try:
            # urllib forces Connection: close, which stalls this provider's gateway.
            # HTTP/1.1 defaults to keep-alive; close locally after reading the bounded response.
            # HTTPSConnection does not follow redirects or forward credentials to other hosts.
            connection.request(
                "POST" if body is not None else "GET",
                endpoint.path + ("?" + endpoint.query if endpoint.query else ""),
                body=body,
                headers=headers,
            )
            with connection.getresponse() as response:
                success = 200 <= response.status < 300
                limit = 8_000_000 if success else 64_000
                raw = response.read(limit + 1)
                try:
                    if len(raw) > limit:
                        raise ValueError("response too large")
                    result = json.loads(raw)
                except (ValueError, RecursionError):
                    if success:
                        raise DeliveryUnavailable(
                            "СДЭК прислал некорректный ответ. Повторите расчёт позже или обратитесь в магазин.",
                            code="cdek_invalid_response",
                        ) from None
                    result = None
                if not success or isinstance(result, dict) and (result.get("errors") or result.get("error")):
                    failure = _provider_failure(path, response.status, result)
                    if failure.code == "cdek_authentication":
                        # Refresh on a later user request; never retry blindly.
                        cache.delete(self.token_key)
                    raise failure
                if not isinstance(result, (dict, list)):
                    raise DeliveryUnavailable(
                        "СДЭК прислал некорректный ответ. Повторите расчёт позже или обратитесь в магазин.",
                        code="cdek_invalid_response",
                    )
                if response_headers is not None:
                    count = response.headers.get("X-Total-Elements", "")
                    if count.isascii() and count.isdigit() and len(count) <= 7:
                        response_headers["X-Total-Elements"] = count
            return result
        except TimeoutError as exc:
            raise DeliveryUnavailable(
                "СДЭК не ответил вовремя. Повторите расчёт через минуту — товары сохранены.",
                code="cdek_timeout",
            ) from exc
        except (HTTPException, OSError, ValueError) as exc:
            raise DeliveryUnavailable(
                "Не удалось связаться со СДЭК. Повторите расчёт через минуту — товары сохранены.",
                code="cdek_connection_failed",
            ) from exc
        finally:
            connection.close()

    def _token(self):
        token = cache.get(self.token_key)
        if token:
            return token
        result = self._request(
            "oauth/token",
            form={
                "grant_type": "client_credentials",
                "client_id": settings.CDEK_CLIENT_ID,
                "client_secret": settings.CDEK_CLIENT_SECRET,
            },
        )
        try:
            token = result["access_token"]
            if not isinstance(token, str) or not token or len(token) > 4096:
                raise ValueError("token")
            ttl = max(1, min(int(result["expires_in"]) - 60, 3600))
        except (KeyError, TypeError, ValueError) as exc:
            raise DeliveryUnavailable("Не удалось подключиться к СДЭК. Повторите расчёт позже.") from exc
        cache.set(self.token_key, token, ttl)
        return token

    def offices(self, filters=None, *, response_headers=None):
        params = {"country_code": "RU", "type": "PVZ", "is_handout": "true"}
        params.update(filters or {})
        result = self._request(
            "deliverypoints", params=params, token=self._token(), response_headers=response_headers
        )
        if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
            raise DeliveryUnavailable("Не удалось получить пункты СДЭК. Повторите поиск позже.")
        return result

    def cities(self, query):
        # Official API /location/cities uses city + country_codes (plural).
        result = self._request(
            "location/cities",
            params={"country_codes": "RU", "city": query, "size": 21, "page": 0, "lang": "rus"},
            token=self._token(),
        )
        if not isinstance(result, list):
            raise DeliveryUnavailable("Не удалось получить города СДЭК. Повторите поиск.")
        cities = []
        for row in result[:20]:
            if (
                not isinstance(row, dict)
                or row.get("country_code") != "RU"
                or type(row.get("code")) is not int
                or not 0 < row["code"] < 10_000_000
                or not isinstance(row.get("city"), str)
                or not row["city"].strip()
            ):
                continue
            cities.append(
                {
                    "code": row["code"],
                    "city": row["city"][:200],
                    "region": row.get("region", "")[:200] if isinstance(row.get("region"), str) else "",
                }
            )
        return {"cities": cities, "has_more": len(result) > 20}

    def office_choices(self, city_code, page):
        return self._office_page({"city_code": city_code}, page, 50)

    def map_points(self, page):
        # Load the carrier directory in bounded pages independently of city/geocoding APIs.
        return self._office_page({}, page, 500)

    def _office_page(self, filters, page, size):
        headers = {}
        result = self.offices({**filters, "page": page, "size": size}, response_headers=headers)
        offices = []
        for row in result[:size]:
            location = row.get("location")
            if (
                row.get("type") != "PVZ"
                or row.get("is_handout") is not True
                or not isinstance(location, dict)
                or location.get("country_code") != "RU"
                or (filters.get("city_code") and location.get("city_code") != filters["city_code"])
                or not isinstance(location.get("address"), str)
                or not location["address"].strip()
            ):
                continue
            try:
                code = safe_code(row.get("code"))
            except DeliveryUnavailable:
                continue
            offices.append(
                {
                    "code": code,
                    "city_code": location.get("city_code")
                    if type(location.get("city_code")) is int
                    else None,
                    "city": str(location.get("city") or "")[:200],
                    "region": str(location.get("region") or "")[:200],
                    "address": location["address"][:500],
                    "name": row.get("name", "")[:200] if isinstance(row.get("name"), str) else "",
                    "work_time": row.get("work_time", "")[:300]
                    if isinstance(row.get("work_time"), str)
                    else "",
                }
            )
            try:
                lat, lon = coordinates(location.get("latitude"), location.get("longitude"))
                offices[-1].update(latitude=lat, longitude=lon)
            except DeliveryUnavailable:
                # An office without coordinates remains selectable in the accessible list.
                offices[-1].update(latitude=None, longitude=None)
        count = headers.get("X-Total-Elements", "")
        # Some environments omit the pagination header. A full page permits one more request.
        has_more = (page + 1) * size < int(count) if count else len(result) >= size
        return {"offices": offices, "next_page": page + 1 if has_more and page < 199 else None}

    def city_at(self, latitude, longitude):
        latitude, longitude = coordinates(latitude, longitude)
        result = self._request(
            "location/coordinates",
            params={"latitude": latitude, "longitude": longitude},
            token=self._token(),
        )
        if (
            not isinstance(result, dict)
            or type(result.get("code")) is not int
            or not 0 < result["code"] < 10_000_000
            or not isinstance(result.get("city"), str)
            or not result["city"].strip()
        ):
            raise DeliveryUnavailable("СДЭК не определил город. Введите его название вручную.")
        # Coordinates lookup may return a foreign city without a country. Verify
        # the code against the Russian directory before offering its pickup points.
        rows = self._request(
            "location/cities",
            params={"code": result["code"], "country_codes": "RU", "size": 1, "lang": "rus"},
            token=self._token(),
        )
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            raise DeliveryUnavailable("СДЭК не определил город в России. Введите город вручную.")
        city = rows[0]
        if city.get("code") != result["code"] or city.get("country_code") != "RU":
            raise DeliveryUnavailable("Выберите город в России — доставка пока доступна только по России.")
        return {
            "city": {
                "code": result["code"],
                "city": result["city"][:200],
                "region": str(city.get("region") or "")[:200],
            }
        }

    def pickup(self, code):
        code = safe_code(code)
        offices = self.offices({"code": code})
        for office in offices:
            location = office.get("location") or {}
            if (
                office.get("code") == code
                and office.get("type") == "PVZ"
                and office.get("is_handout") is True
                and isinstance(location, dict)
                and location.get("country_code") == "RU"
            ):
                try:
                    city_code = int(location["city_code"])
                    city, address = location["city"], location["address"]
                    if (
                        city_code <= 0
                        or not isinstance(city, str)
                        or not isinstance(address, str)
                        or not address
                    ):
                        raise ValueError("address")
                except (KeyError, TypeError, ValueError) as exc:
                    raise DeliveryUnavailable(
                        "Адрес пункта не подтверждён СДЭК. Выберите другой пункт."
                    ) from exc
                limits = _weight_limits(office.get("weight_min"), office.get("weight_max"), unit=1000)
                return {
                    "code": code,
                    "city_code": city_code,
                    "city": city,
                    "address": address,
                    "name": str(office.get("name", code))[:200],
                    "weight_min_g": str(limits[0]),
                    "weight_max_g": str(limits[1]),
                }
        raise DeliveryUnavailable("Этот пункт СДЭК недоступен для выдачи. Выберите другой пункт.")

    def calculate(self, tariff, pickup, packages, *, declared_value=None):
        minimum_weight, maximum_weight = _weight_limits(
            pickup.get("weight_min_g"), pickup.get("weight_max_g")
        )
        if not packages or any(
            not isinstance(package, dict) or type(package.get("weight")) is not int or package["weight"] <= 0
            for package in packages
        ):
            raise DeliveryUnavailable("Не удалось проверить вес упаковок. Повторите расчёт доставки.")
        # CDEK's official widget applies PVZ limits to each cargo place, not their sum:
        # https://github.com/cdek-it/widget/blob/main/dist/cdek-widget.es.js
        if any(
            package["weight"] < minimum_weight or maximum_weight and package["weight"] > maximum_weight
            for package in packages
        ):
            raise DeliveryUnavailable(
                "Этот пункт не принимает отправления такого веса. Выберите другой пункт."
            )
        payload = {
            "type": 1,
            "currency": 1,
            "tariff_code": tariff,
            "from_location": {"code": settings.CDEK_FROM_CITY_CODE},
            "to_location": {"code": pickup["city_code"]},
            "packages": packages,
        }
        if declared_value is not None:
            try:
                value = Decimal(str(declared_value))
                if (
                    isinstance(declared_value, bool)
                    or not value.is_finite()
                    or not 0 < value <= Decimal("9999999.99")
                    or value != value.quantize(Decimal("0.01"))
                ):
                    raise ValueError("declared value")
            except (DecimalException, TypeError, ValueError) as exc:
                raise DeliveryUnavailable(
                    "Не удалось подтвердить объявленную стоимость товаров. Проверьте корзину."
                ) from exc
            # Official integration: INSURANCE parameter is the merchandise value,
            # not a fee or percentage. Let CDEK apply the account's actual rate.
            # https://github.com/cdek-it/wordpress/blob/main/src/Actions/CalculateDeliveryAction.php
            # SDK uses a JSON number; bounded two-decimal amounts retain their cents
            # in Python's JSON float serialization. Arithmetic above stays Decimal.
            payload["services"] = [{"code": "INSURANCE", "parameter": float(value)}]
        result = self._request("calculator/tariff", token=self._token(), payload=payload)
        try:
            # total_sum includes VAT and services; delivery_sum alone can undercharge.
            price = Decimal(str(result["total_sum"]))
            if not all(type(result[key]) is int for key in ("period_min", "period_max")):
                raise ValueError("period must be integer")
            minimum, maximum = result["period_min"], result["period_max"]
            if (
                not price.is_finite()
                or price <= 0
                or price > Decimal("9999999.99")
                or price != price.quantize(Decimal("0.01"))
                or not 0 <= minimum <= maximum <= 365
            ):
                raise ValueError("quote")
            if result.get("currency", "RUB") not in {"RUB", 1}:
                raise ValueError("currency")
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise DeliveryUnavailable(
                "СДЭК не подтвердил стоимость и срок. Выберите другой пункт или повторите позже."
            ) from exc
        return {"price": str(price.quantize(Decimal("0.01"))), "period_min": minimum, "period_max": maximum}
