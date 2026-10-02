"""CDEK API v2 boundary. Credentials and arbitrary upstream URLs never reach the widget."""

import hashlib
import json
import math
import re
from http.client import HTTPSConnection, HTTPException
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError


class DeliveryUnavailable(ValidationError):
    pass


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
    def __init__(self):
        if not configured():
            raise DeliveryUnavailable("Расчёт СДЭК пока не подключён. Товары сохранятся в корзине.")
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
        connection = HTTPSConnection(endpoint.hostname, timeout=getattr(settings, "CDEK_TIMEOUT_SECONDS", 10))
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
                if not 200 <= response.status < 300:
                    raise ValueError("provider status")
                raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise ValueError("response too large")
                result = json.loads(raw)
                if response_headers is not None:
                    count = response.headers.get("X-Total-Elements", "")
                    if count.isascii() and count.isdigit() and len(count) <= 7:
                        response_headers["X-Total-Elements"] = count
            if not isinstance(result, (dict, list)) or isinstance(result, dict) and result.get("errors"):
                raise ValueError("invalid response")
            return result
        except (HTTPException, TimeoutError, OSError, ValueError) as exc:
            raise DeliveryUnavailable(
                "СДЭК не ответил на запрос. Повторите расчёт через минуту — товары сохранены."
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
                try:
                    limits = [
                        Decimal(str(office.get(key) or 0)) * 1000 for key in ("weight_min", "weight_max")
                    ]
                    if any(not value.is_finite() or value < 0 for value in limits):
                        raise ValueError("weight restriction")
                except (InvalidOperation, ValueError) as exc:
                    raise DeliveryUnavailable(
                        "Не удалось проверить ограничения пункта. Выберите другой пункт."
                    ) from exc
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

    def calculate(self, tariff, pickup, packages):
        # The official widget converts office limits from kilograms to grams.
        weight = sum(package["weight"] for package in packages)
        minimum_weight = Decimal(pickup.get("weight_min_g", "0"))
        maximum_weight = Decimal(pickup.get("weight_max_g", "0"))
        if weight < minimum_weight or maximum_weight and weight > maximum_weight:
            raise DeliveryUnavailable(
                "Этот пункт не принимает отправления такого веса. Выберите другой пункт."
            )
        result = self._request(
            "calculator/tariff",
            token=self._token(),
            payload={
                "type": 1,
                "currency": 1,
                "tariff_code": tariff,
                "from_location": {"code": settings.CDEK_FROM_CITY_CODE},
                "to_location": {"code": pickup["city_code"]},
                "packages": packages,
            },
        )
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
