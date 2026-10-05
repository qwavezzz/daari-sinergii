"""Private VPS acceptance: real CDEK quote and a labelled, unpaid test order.

Uses checkout views with CSRF, two hidden QA products and fictional box prices.
Only this process admits test packing profiles. No measurements are confirmed,
no public settings are changed, and no bank payment or shipment is created.
The regular worker sends the two queued creation emails after commit.
"""

import argparse
from collections import Counter
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sys
import uuid
from unittest.mock import patch


BOX_CODES = ("demo-auto-small", "demo-auto-shared", "demo-auto-large")
SOURCE_SKUS = ("DEMO-AUTO-A", "DEMO-AUTO-B")
BOX_PRICE = Decimal("50.00")  # Fictional test price, never saved to box records.
PICKUP_CODE = "MSK2"
DEFAULT_RUN = "packing-msk2-20261005"


def identifiers(run_id):
    from django.conf import settings
    from deploy.check_unpaid_order import require

    require(bool(re.fullmatch(r"[a-z0-9-]{1,30}", run_id)), "Invalid run ID")
    key = uuid.uuid5(uuid.NAMESPACE_URL, settings.SHOP_ORIGIN.rstrip("/") + "/qa/packing/" + run_id)
    marker = (
        f"QA {run_id}: тест упаковки и СДЭК TLT4 → MSK2. НЕ СОБИРАТЬ И НЕ ОТПРАВЛЯТЬ. "
        "Замеры учебные; 50 ₽ за коробку — условная цена, не прайс СДЭК."
    )
    return key, marker


def validate_modes():
    from django.conf import settings
    from apps.orders.cdek import configured
    from deploy.check_unpaid_order import require, validate_modes as unpaid_modes

    unpaid_modes()
    require(configured() and not settings.CDEK_TEST_MODE, "Working CDEK credentials required")
    require(not settings.CDEK_DEMO_QUOTES_ENABLED, "Demo CDEK quotes must be disabled")
    require(
        settings.CDEK_FROM_CITY_CODE == 431 and settings.CDEK_FROM_PVZ_CODE == "TLT4",
        "Expected sender 431 / TLT4",
    )


def validate_order(order, marker):
    from deploy.check_unpaid_order import require, validate_order as unpaid_order

    unpaid_order(order, marker)
    shipping = order.delivery_snapshot
    require(order.delivery_type == "cdek_pvz", "Wrong delivery type")
    require(shipping.get("price_source") == "cdek", "Quote did not come from CDEK")
    require(shipping.get("test_mode") is False, "Expected working CDEK environment")
    require(shipping["sender"]["code"] == "TLT4", "Wrong sender PVZ")
    require(shipping["pickup"]["code"] == PICKUP_CODE, "Wrong recipient PVZ")
    require(shipping["tariff_code"] == 136, "Wrong tariff")
    expected_address = f"{shipping['pickup']['city']}, {shipping['pickup']['address']}"
    require(order.address == expected_address, "Saved address differs from selected PVZ")
    plan = shipping["packing"]
    require(not plan["measurements_confirmed"], "Fictional measurements were marked confirmed")
    require(len(plan["parcels"]) == len(shipping["packages"]) == 1, "Expected one shared box")
    parcel = plan["parcels"][0]
    require(parcel["test_only"] and parcel["box_code"] in BOX_CODES, "Unexpected box profile")
    require(len(parcel["placements"]) == 2, "Expected two protected units")
    contents = Counter()
    for row in parcel["contents"]:
        contents[row["product_id"]] += row["quantity"]
    items = list(order.items.all())
    require(len(items) == 2 and all(i.quantity == 1 for i in items), "Unexpected order items")
    require(contents == Counter({i.product_id: i.quantity for i in items}), "Packing differs from order")
    subtotal = sum((i.unit_price * i.quantity for i in items), Decimal("0.00"))
    require(order.subtotal == subtotal == Decimal("2580.00"), "Unexpected goods subtotal")
    require(Decimal(shipping["declared_value"]) == subtotal, "Incorrect insurance amount")
    require(Decimal(shipping["packing_price"]) == BOX_PRICE, "Wrong per-box charge")
    require(Decimal(plan["packing_price"]) == Decimal(parcel["packing_price"]) == BOX_PRICE, "Wrong plan fee")
    require(Decimal(shipping["carrier_price"]) > 0, "Carrier price must be positive")
    require(
        order.delivery_price == Decimal(shipping["price"]) == Decimal(shipping["carrier_price"]) + BOX_PRICE,
        "Delivery total differs from carrier plus packaging",
    )
    require(order.total == subtotal + order.delivery_price, "Wrong order total")


def check_access(order, client):
    from deploy.check_unpaid_order import check_access as unpaid_access

    unpaid_access(order, client)


def create_check(buyer_email, run_id=DEFAULT_RUN):
    from django.conf import settings
    from django.core.validators import validate_email
    from django.db import connection, transaction
    from django.test import override_settings
    from apps.catalog.models import Product
    from apps.orders.auto_profiles import UNIT_FIELDS
    from apps.orders.automatic_packing import AutomaticPacking
    from apps.orders.cdek import CdekClient
    from apps.orders.models import DeliveryMethod, Order, PackingBox
    from apps.orders.notifications import manager_email
    from deploy.check_unpaid_order import CheckoutInputs, new_client, require

    validate_modes()
    buyer_email = buyer_email.strip()
    validate_email(buyer_email)
    require(buyer_email.casefold() != manager_email().casefold(), "Use a separate customer mailbox")
    key, marker = identifiers(run_id)
    with transaction.atomic(), override_settings(PAYMENT_STUB_ENABLED=False):
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                cursor.execute("SET LOCAL statement_timeout = '30s'")
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key.int % (2**63)])
        existing = Order.objects.select_for_update().filter(checkout_key=key).first()
        if existing:
            validate_order(existing, marker)
            require(existing.email.casefold() == buyer_email.casefold(), "Run belongs to another mailbox")
            return existing.pk, False

        sources = list(Product.objects.filter(sku__in=SOURCE_SKUS).order_by("sku"))
        boxes = list(PackingBox.objects.filter(code__in=BOX_CODES).order_by("pk"))
        require(len(sources) == 2 and len(boxes) == 3, "Run setup_auto_packing --with-demo first")
        require(
            all(
                p.unit_test_only
                and not p.unit_measurement_signature
                and p.status == "draft"
                and not p.purchasable
                and p.shipping_mode == "automatic"
                and p.price == Decimal("1290.00")
                for p in sources
            ),
            "Source profiles must remain unpublished fictional demo products at 1290 RUB",
        )
        require(
            all(
                b.auto_test_only and not b.auto_measurement_signature and b.active and b.auto_enabled
                for b in boxes
            ),
            "Only unconfirmed demo boxes allowed",
        )
        source_before = list(Product.objects.filter(sku__in=SOURCE_SKUS).order_by("sku").values())
        boxes_before = list(PackingBox.objects.filter(code__in=BOX_CODES).order_by("pk").values())
        methods_before = list(DeliveryMethod.objects.order_by("pk").values())
        method = (
            DeliveryMethod.objects.select_for_update()
            .filter(active=True, type="cdek_pvz", cdek_tariff_code=136)
            .order_by("pk")
            .first()
        )
        require(method is not None, "No active CDEK delivery method with tariff 136")
        products = []
        for source in sources:
            suffix = source.sku[-1]
            # INSERT and final unpublication share one transaction. Public readers
            # never see these products as published or available for purchase.
            products.append(
                Product.objects.create(
                    name=f"[ТЕСТ] Автоупаковка {suffix} — не отправлять",
                    sku=f"DEMO-PACK-QA-{key.hex}-{suffix}",
                    slug=f"demo-pack-qa-{key.hex}-{suffix.lower()}",
                    price=source.price,
                    stock=1,
                    status="published",
                    purchasable=True,
                    description=marker,
                    vat_code=source.vat_code,
                    **{field: getattr(source, field) for field in UNIT_FIELDS},
                )
            )
        for box in boxes:
            box.auto_price_mode, box.auto_price = "charge", BOX_PRICE

        actual_request = CdekClient._request

        def calculation_only(client, path, **kwargs):
            require(
                path in {"oauth/token", "deliverypoints", "calculator/tariff"}, "Unexpected CDEK operation"
            )
            require(client.base == "https://api.cdek.ru/v2", "Unexpected CDEK endpoint")
            return actual_request(client, path, **kwargs)

        def private_packing(items, **kwargs):
            require({i.product_id for i in items} <= {p.pk for p in products}, "Unexpected cart products")
            return AutomaticPacking(items, allow_test=True)

        with (
            patch("apps.orders.automatic_packing.available_boxes", return_value=boxes),
            patch("apps.orders.packing.AutomaticPacking", side_effect=private_packing),
            patch.object(CdekClient, "_request", calculation_only),
        ):
            client = new_client()
            for product in products:
                page = client.get(f"/products/{product.slug}/", secure=True)
                require(page.status_code == 200, "QA product page unavailable")
                csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
                added = client.post(
                    f"/cart/add/{product.pk}/", {"quantity": 1, "csrfmiddlewaretoken": csrf}, secure=True
                )
                require(added.status_code == 302, "Cart addition failed")
            page = client.get("/checkout/", secure=True)
            require(page.status_code == 200, "Checkout unavailable")
            parser = CheckoutInputs()
            parser.feed(page.content.decode())
            require(bool(parser.values.get("quote_token")), "Missing checkout quote")
            quoted = client.post(
                "/checkout/cdek/quote/",
                {
                    **parser.values,
                    "delivery_method": str(method.pk),
                    "pvz_code": PICKUP_CODE,
                },
                secure=True,
            )
            if quoted.status_code != 200:
                # The view returns a curated message, not credentials or raw API payloads.
                message = (
                    quoted.json().get("message", "")
                    if quoted.get("Content-Type", "").startswith("application/json")
                    else ""
                )
                require(False, f"CDEK quote failed: HTTP {quoted.status_code}; {message}; no order committed")
            result = quoted.json()
            data = {
                **parser.values,
                "checkout_key": str(key),
                "first_name": "Проверка",
                "last_name": "Упаковки",
                "phone_country": "RU",
                "phone": "9990000000",
                "email": buyer_email,
                "delivery_method": str(method.pk),
                "confirmed_delivery": str(method.pk),
                "pvz_code": PICKUP_CODE,
                "delivery_quote": result["delivery_quote"],
                "quote_token": result["quote_token"],
                "accept_terms": "on",
                "comment": marker,
                "total": "0.01",
                "delivery_price": "0.01",
                "address": "FORGED ADDRESS",
            }
            for changes, expected in (({"csrfmiddlewaretoken": ""}, 403), ({"pvz_code": "TLT2"}, 422)):
                rejected = client.post("/checkout/", {**data, **changes}, secure=True)
                require(rejected.status_code == expected, "Invalid checkout was not rejected")
                require(not Order.objects.filter(checkout_key=key).exists(), "Rejected request created order")
            first = client.post("/checkout/", data, secure=True)
            require(first.status_code == 302, f"Checkout failed: HTTP {first.status_code}")
            order = Order.objects.get(checkout_key=key)
            validate_order(order, marker)
            require(first["Location"] == order.get_absolute_url(), "Unexpected checkout redirect")
            again = client.post("/checkout/", data, secure=True)
            require(again.status_code == 302 and again["Location"] == first["Location"], "Repeat POST failed")
            require(Order.objects.filter(checkout_key=key).count() == 1, "Duplicate order")
            check_access(order, client)

        require(order.reservations.filter(state="active", quantity=1).count() == 2, "Incorrect reservations")
        notices = order.notifications.filter(event="created")
        require(notices.count() == 2, "Expected two creation notices")
        require(
            set(notices.values_list("recipient", flat=True)) == {buyer_email, manager_email()},
            "Wrong email recipients",
        )
        Product.objects.filter(pk__in=[p.pk for p in products]).update(status="draft", purchasable=False)
        require(
            Product.objects.filter(
                pk__in=[p.pk for p in products], stock=1, reserved_stock=1, status="draft", purchasable=False
            ).count()
            == 2,
            "QA products must remain hidden with valid stock reservations",
        )
        require(
            source_before == list(Product.objects.filter(sku__in=SOURCE_SKUS).order_by("sku").values()),
            "Source products changed",
        )
        require(
            boxes_before == list(PackingBox.objects.filter(code__in=BOX_CODES).order_by("pk").values()),
            "Box records changed",
        )
        require(
            methods_before == list(DeliveryMethod.objects.order_by("pk").values()), "Delivery methods changed"
        )
        return order.pk, True


def status_check(run_id=DEFAULT_RUN):
    from apps.orders.models import Order

    key, marker = identifiers(run_id)
    order = Order.objects.get(checkout_key=key)
    validate_order(order, marker)
    shipping = order.delivery_snapshot
    return {
        "order_id": str(order.public_id),
        "status": order.status,
        "payment": order.financial_status,
        "test_order": order.test_mode,
        "sender": shipping["sender"],
        "pickup": shipping["pickup"],
        "tariff": shipping["tariff_code"],
        "packing": shipping["packing"],
        "comparison": shipping["packing_comparison"],
        "carrier_rub": shipping["carrier_price"],
        "packaging_rub": shipping["packing_price"],
        "delivery_rub": str(order.delivery_price),
        "goods_rub": str(order.subtotal),
        "order_total_rub": str(order.total),
        "reservations": list(order.reservations.values("state", "quantity", "expires_at")),
        "notifications": list(order.notifications.values("event", "audience", "attempts", "sent_at")),
        "shipment_created": False,
        "bank_payment_created": False,
    }


def cancel_check(run_id=DEFAULT_RUN):
    from django.db import transaction
    from apps.orders.models import Order
    from apps.orders.services import transition_order
    from deploy.check_unpaid_order import require

    validate_modes()
    key, marker = identifiers(run_id)
    with transaction.atomic():
        order = Order.objects.select_for_update().get(checkout_key=key)
        validate_order(order, marker)
        transition_order(order.pk, "canceled")
        require(not order.reservations.filter(state="active").exists(), "Reservations not released")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "status", "cancel"])
    parser.add_argument("--run-id", default=DEFAULT_RUN)
    args = parser.parse_args()
    sys.path.insert(0, str(Path.cwd()))
    import django

    django.setup()
    from django.conf import settings
    from django.db import connection
    from deploy.check_unpaid_order import CheckFailed, require

    try:
        require(connection.vendor == "postgresql", "VPS acceptance requires PostgreSQL")
        require(settings.SHOP_ORIGIN.rstrip("/") == "https://shop.dari-sinergii.ru", "Unexpected shop origin")
        created = False
        if args.action == "create":
            _, created = create_check(os.environ.get("DARI_QA_BUYER_EMAIL", ""), args.run_id)
        elif args.action == "cancel":
            cancel_check(args.run_id)
        result = {"created_now": created, **status_check(args.run_id)}
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        print("PACKING_ORDER_CHECK_OK; FICTIONAL_MEASUREMENTS_AND_BOX_PRICE; NO_SHIPMENT_OR_BANK_PAYMENT")
    except Exception as exc:
        detail = str(exc) if isinstance(exc, CheckFailed) else type(exc).__name__
        print("PACKING_ORDER_CHECK_STOPPED: " + detail, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
