"""Signed, session-bound quotes; only this module establishes CDEK checkout totals."""

import hashlib
from decimal import Decimal
from time import monotonic

from django.conf import settings
from django.core import signing
from django.utils import timezone

from .cdek import CdekClient, DeliveryUnavailable, TariffUnavailable, configured, safe_code
from .packing import MAX_PACKING_OPTIONS, PreparedPacking, package_key, packing_plan

# Old quotes do not attest to the measured packing plan.
QUOTE_SALT = "cdek-delivery-quote-v4-compared-packing"
COMPARISON_SECONDS = 20


def shipment_identity():
    return [
        getattr(settings, "CDEK_TEST_MODE", True),
        getattr(settings, "CDEK_FROM_CITY_CODE", 0),
        hashlib.sha256(getattr(settings, "CDEK_CLIENT_ID", "").encode()).hexdigest(),
    ]


def packages_for(cart):
    return packing_plan(cart)["packages"]


def quote_delivery(cart, method, code, session_key):
    from .services import checkout_snapshot, quote_data, QuoteChanged

    deadline = monotonic() + COMPARISON_SECONDS
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
    # Reuse the validated input when PVZ restrictions alter admissible plans.
    options = prepared.options(pickup=pickup, limit=MAX_PACKING_OPTIONS)
    best = None
    seen = set()
    attempted = successful = rejected = 0
    for candidate in options:
        key = tuple(sorted(package_key(package) for package in candidate["packages"]))
        if key in seen:
            continue
        if monotonic() >= deadline:
            break
        seen.add(key)
        attempted += 1
        try:
            quoted = client.calculate(
                method.cdek_tariff_code, pickup, candidate["packages"], declared_value=subtotal
            )
        except TariffUnavailable:
            rejected += 1
            continue
        # Network/auth/malformed-response failures are not evidence of an
        # infeasible packing. Propagate them rather than silently dropping it.
        successful += 1
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
        "method_id": method.pk,
        "tariff_code": method.cdek_tariff_code,
        "pickup": pickup,
        "packages": packages,
        "packing": plan,
        "packing_comparison": {
            "options": len(options),
            "attempted": attempted,
            "successful": successful,
            "rejected": rejected,
            "finished": attempted == len(options),
            "scope": "bounded_measured_options",
        },
        "origin_city_code": settings.CDEK_FROM_CITY_CODE,
        "test_mode": settings.CDEK_TEST_MODE,
        "waybill": "manual",
        "currency": "RUB",
        "declared_value": str(subtotal),
        "services": [{"code": "INSURANCE", "parameter": str(subtotal)}],
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
