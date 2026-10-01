"""Signed, session-bound quotes; only this module establishes CDEK checkout totals."""

import hashlib
from decimal import Decimal

from django.conf import settings
from django.core import signing
from django.utils import timezone

from .cdek import CdekClient, DeliveryUnavailable, configured, safe_code

PACKAGE_FIELDS = ("package_weight_g", "package_length_cm", "package_width_cm", "package_height_cm")
QUOTE_SALT = "cdek-delivery-quote-v1"


def shipment_identity():
    return [
        getattr(settings, "CDEK_TEST_MODE", True),
        getattr(settings, "CDEK_FROM_CITY_CODE", 0),
        hashlib.sha256(getattr(settings, "CDEK_CLIENT_ID", "").encode()).hexdigest(),
    ]


def packages_for(cart):
    packages = []
    for item in cart.items.select_related("product").order_by("product_id"):
        values = [getattr(item.product, field) for field in PACKAGE_FIELDS]
        if not all(isinstance(value, int) and value > 0 for value in values):
            raise DeliveryUnavailable(
                f"Для «{item.product.name}» ещё не настроена упаковка. Расчёт доставки пока недоступен."
            )
        # Every unit ships in its individually measured parcel. No guessed consolidation.
        if len(packages) + item.quantity > 100:
            raise DeliveryUnavailable(
                "Для такого количества товаров свяжитесь с магазином для расчёта доставки."
            )
        packages.extend(
            [dict(zip(("weight", "length", "width", "height"), values)) for _ in range(item.quantity)]
        )
    if not packages:
        raise DeliveryUnavailable("Добавьте товары в корзину перед расчётом доставки.")
    return packages


def quote_delivery(cart, method, code, session_key):
    from .services import checkout_snapshot, quote_data, QuoteChanged

    if not configured():
        raise DeliveryUnavailable("Расчёт СДЭК пока не подключён. Товары сохранятся в корзине.")
    if cart.session_key != session_key or method.type != "cdek_pvz" or not method.active:
        raise DeliveryUnavailable("Выберите доступный способ доставки СДЭК.")
    if not method.cdek_tariff_code:
        raise DeliveryUnavailable("Тариф СДЭК ещё не настроен. Свяжитесь с магазином.")
    # Take a short locked snapshot, then release DB locks before doing network I/O.
    _, cart_token = checkout_snapshot(cart)
    bound = signing.loads(cart_token, salt="checkout-quote")
    bound_method = next((row for row in bound["delivery"] if row[0] == method.pk), None)
    if not bound_method or bound_method[5:] != [method.type, method.cdek_tariff_code]:
        raise QuoteChanged("Способ доставки изменился. Обновите страницу и повторите расчёт.")
    packages = packages_for(cart)
    client = CdekClient()
    pickup = client.pickup(safe_code(code))
    result = client.calculate(method.cdek_tariff_code, pickup, packages)
    cart.refresh_from_db()
    if bound != quote_data(cart):
        raise QuoteChanged("Корзина изменилась во время расчёта. Повторите расчёт доставки.")
    now = timezone.now()
    snapshot = {
        "provider": "cdek",
        "method_id": method.pk,
        "tariff_code": method.cdek_tariff_code,
        "pickup": pickup,
        "packages": packages,
        "origin_city_code": settings.CDEK_FROM_CITY_CODE,
        "test_mode": settings.CDEK_TEST_MODE,
        "waybill": "manual",
        "currency": "RUB",
        "quoted_at": now.isoformat(),
        **result,
    }
    token = signing.dumps(
        {"cart": bound, "shipping": snapshot, "identity": shipment_identity()}, salt=QUOTE_SALT, compress=True
    )
    subtotal = sum(Decimal(row[2]) * row[1] for row in bound["items"])
    return {
        "delivery_quote": token,
        "quote_token": cart_token,
        "shipping": snapshot,
        "total": str(subtotal + Decimal(result["price"])),
        "expires_in": getattr(settings, "CDEK_QUOTE_TTL_SECONDS", 900),
    }


def verified_delivery(cart, method, token, code):
    from .services import quote_data, QuoteChanged

    try:
        data = signing.loads(
            token or "", salt=QUOTE_SALT, max_age=getattr(settings, "CDEK_QUOTE_TTL_SECONDS", 900)
        )
        snapshot = data["shipping"]
        valid = (
            configured()
            and data["cart"] == quote_data(cart)
            and data["identity"] == shipment_identity()
            and snapshot["method_id"] == method.pk
            and snapshot["tariff_code"] == method.cdek_tariff_code
            and snapshot["pickup"]["code"] == safe_code(code or "")
        )
    except (signing.BadSignature, KeyError, TypeError, DeliveryUnavailable):
        valid = False
    if not valid:
        raise QuoteChanged(
            "Расчёт доставки устарел или пункт изменился. Выберите пункт и рассчитайте доставку снова."
        )
    return snapshot
