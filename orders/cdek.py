"""CDEK API v2 boundary. Credentials and arbitrary upstream URLs never reach the widget."""

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

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


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


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
        headers = {"Accept": "application/json", "X-App-Name": "dari-sinergii"}
        body = None
        if token:
            headers["Authorization"] = "Bearer " + token
        if form is not None:
            body = urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        try:
            with build_opener(NoRedirect).open(
                Request(url, data=body, headers=headers),
                timeout=getattr(settings, "CDEK_TIMEOUT_SECONDS", 10),
            ) as response:
                raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise ValueError("response too large")
                result = json.loads(raw)
                if response_headers is not None:
                    count = response.headers.get("X-Total-Elements", "")
                    if count.isdigit():
                        response_headers["X-Total-Elements"] = count
            if not isinstance(result, (dict, list)) or isinstance(result, dict) and result.get("errors"):
                raise ValueError("invalid response")
            return result
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raise DeliveryUnavailable(
                "СДЭК не ответил на запрос. Повторите расчёт через минуту — товары сохранены."
            ) from exc

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

    def pickup(self, code):
        code = safe_code(code)
        offices = self.offices({"code": code})
        for office in offices:
            location = office.get("location") or {}
            if (
                office.get("code") == code
                and office.get("type") == "PVZ"
                and office.get("is_handout") is True
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
            price = Decimal(str(result["delivery_sum"]))
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
