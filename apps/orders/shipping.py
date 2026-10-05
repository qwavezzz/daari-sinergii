"""Signed, session-bound quotes; only this module establishes CDEK checkout totals."""

import hashlib
from decimal import Decimal
from time import monotonic

from django.conf import settings
from django.core import signing
from django.utils import timezone

from .cdek import CdekClient, DeliveryUnavailable, TariffUnavailable, _weight_limits, configured, safe_code
from .packing import MAX_PACKING_OPTIONS, PreparedPacking, package_key, packing_plan

# Old quotes do not attest to the measured packing plan.
QUOTE_SALT = "cdek-delivery-quote-v4-compared-packing"
COMPARISON_SECONDS = 20
DEMO_DELIVERY_PRICE = Decimal("500.00")


def demo_quotes_enabled():
    enabled = getattr(settings, "CDEK_DEMO_QUOTES_ENABLED", False)
    if enabled and (
        not settings.CDEK_TEST_MODE or not settings.PAYMENT_STUB_ENABLED or settings.ALFABANK_ENABLED
    ):
        raise DeliveryUnavailable(
            "Учебная доставка доступна только с пробной оплатой, "
            "выключенным Альфа-Банком и тестовой средой СДЭК."
        )
    return enabled


def shipment_identity():
    return [
        getattr(settings, "CDEK_TEST_MODE", True),
        getattr(settings, "CDEK_FROM_CITY_CODE", 0),
        getattr(settings, "CDEK_FROM_PVZ_CODE", ""),
        hashlib.sha256(getattr(settings, "CDEK_CLIENT_ID", "").encode()).hexdigest(),
        "demo:" + str(DEMO_DELIVERY_PRICE) if demo_quotes_enabled() else "cdek",
    ]


def packages_for(cart):
    return packing_plan(cart)["packages"]


def quote_delivery(cart, method, code, session_key):
    from .services import checkout_snapshot, quote_data, QuoteChanged

    deadline = monotonic() + COMPARISON_SECONDS
    demo = demo_quotes_enabled()
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
    prepared = PreparedPacking(cart)
    # Bind the exact loaded data used by the planner, not a second fresh read.
    # Otherwise A -> B -> A edits around the carrier call could price B while
    # both surrounding fingerprints describe A.
    if bound != quote_data(cart, items=prepared.items, packing=prepared.configuration):
        raise QuoteChanged("Условия упаковки изменились во время расчёта. Повторите расчёт доставки.")
    # Fail before any network call when the composition has no measured cover.
    prepared.options(limit=1)
    subtotal = sum(Decimal(row[2]) * row[1] for row in bound["items"])
    client = CdekClient()
    client.deadline = deadline
    pickup = client.pickup(safe_code(code))
    sender = client.shipment_point() if getattr(settings, "CDEK_FROM_PVZ_CODE", "") else None
    limits = pickup
    if sender:
        recipient_limits = _weight_limits(pickup.get("weight_min_g"), pickup.get("weight_max_g"))
        sender_limits = _weight_limits(sender.get("weight_min_g"), sender.get("weight_max_g"))
        maximums = [value for value in (recipient_limits[1], sender_limits[1]) if value]
        limits = {
            **pickup,
            "weight_min_g": str(max(recipient_limits[0], sender_limits[0])),
            "weight_max_g": str(min(maximums) if maximums else 0),
        }
    # Reuse the validated input when PVZ restrictions alter admissible plans.
    options = prepared.options(pickup=limits, limit=MAX_PACKING_OPTIONS)
    best = None
    seen = set()
    attempted = successful = rejected = 0
    for candidate in options:
        key = (
            tuple(sorted(package_key(package) for package in candidate["packages"])),
            candidate["packing_price"],
        )
        if key in seen:
            continue
        if monotonic() >= deadline:
            break
        seen.add(key)
        attempted += 1
        try:
            quoted = (
                {"price": str(DEMO_DELIVERY_PRICE), "period_min": None, "period_max": None}
                if demo
                else client.calculate(
                    method.cdek_tariff_code, pickup, candidate["packages"], declared_value=subtotal
                )
            )
        except TariffUnavailable:
            rejected += 1
            continue
        # Network/auth/malformed-response failures are not evidence of an
        # infeasible packing. Propagate them rather than silently dropping it.
        successful += 1
        carrier_price = Decimal(quoted["price"])
        packing_price = Decimal("0.00") if demo else Decimal(candidate["packing_price"])
        if carrier_price + packing_price > Decimal("9999999.99"):
            raise DeliveryUnavailable("Стоимость доставки требует проверки сотрудником магазина.")
        quoted = {
            **quoted,
            "carrier_price": str(carrier_price),
            "packing_price": str(packing_price),
            "price": str(carrier_price + packing_price),
        }
        score = (
            Decimal(quoted["price"]),
            len(candidate["packages"]),
            sum(p["length"] * p["width"] * p["height"] for p in candidate["packages"]),
            sum(p["weight"] for p in candidate["packages"]),
        )
        if best is None or score < best[0]:
            best = (score, candidate, quoted)
    if best is None:
        if attempted < len(options):
            raise DeliveryUnavailable(
                "Не удалось завершить сравнение упаковок. Повторите расчёт или свяжитесь с магазином."
            )
        raise TariffUnavailable(
            "СДЭК не подтвердил тариф для проверенных вариантов упаковки. "
            "Выберите другой пункт или свяжитесь с магазином для подбора доставки."
        )
    _, plan, result = best
    packages = plan["packages"]
    cart.refresh_from_db()
    if bound != quote_data(cart):
        raise QuoteChanged("Корзина изменилась во время расчёта. Повторите расчёт доставки.")
    now = timezone.now()
    snapshot = {
        "provider": "cdek",
        "price_source": "demo" if demo else "cdek",
        "method_id": method.pk,
        "tariff_code": method.cdek_tariff_code,
        "pickup": pickup,
        "sender": sender,
        "packages": packages,
        "packing": plan,
        "packing_comparison": {
            "options": len(options),
            "attempted": attempted,
            "successful": successful,
            "rejected": rejected,
            "finished": attempted == len(options),
            "scope": "demo_fixed_price"
            if demo
            else ("bounded_automatic_options" if prepared.automatic else "bounded_measured_options"),
        },
        "origin_city_code": settings.CDEK_FROM_CITY_CODE,
        "test_mode": settings.CDEK_TEST_MODE,
        "waybill": "none" if demo else "manual",
        "currency": "RUB",
        "declared_value": str(subtotal),
        "services": [] if demo else [{"code": "INSURANCE", "parameter": str(subtotal)}],
        "quoted_at": now.isoformat(),
        **result,
    }
    token = signing.dumps(
        {"cart": bound, "shipping": snapshot, "identity": shipment_identity()}, salt=QUOTE_SALT, compress=True
    )
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
