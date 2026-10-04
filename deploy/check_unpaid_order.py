"""Operator-only unpaid-order acceptance; use production env, no public configuration changes.

Creates one labelled DEMO order via the actual checkout view with CSRF enforcement.
Its static delivery method exists only inside one PostgreSQL transaction and is
deleted before commit. The normal worker sends queued mail after commit. No bank
or carrier calls are made. Repeating a run ID reuses the order; cancel releases it.
"""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import uuid
from html.parser import HTMLParser
from urllib.parse import urlsplit


class CheckFailed(Exception):
    pass


def require(condition, message):
    if not condition:
        raise CheckFailed(message)


def identifiers(run_id):
    from django.conf import settings

    require(bool(re.fullmatch(r"[a-z0-9-]{1,30}", run_id)), "Invalid run ID")
    key = uuid.uuid5(uuid.NAMESPACE_URL, settings.SHOP_ORIGIN.rstrip("/") + "/qa/" + run_id)
    return key, f"QA {run_id}: проверка неоплаченного заказа; не собирать и не отправлять."


def validate_modes():
    from django.conf import settings
    from apps.orders.notifications import validate_configuration

    require(not settings.DEBUG and not settings.DEVELOPMENT, "Secure production settings required")
    require(
        not settings.ALFABANK_ENABLED and settings.ALFABANK_TEST_MODE and not settings.ALFABANK_LIVE_APPROVED,
        "This check requires disabled bank payments and test mode",
    )
    require(settings.CHECKOUT_ENABLED, "Checkout is disabled")
    require(settings.SHOP_ORIGIN.startswith("https://"), "HTTPS shop origin required")
    validate_configuration()


def validate_order(order, marker):
    from apps.payments.models import PaymentAttempt, TrialPayment

    require(order.test_mode and order.comment == marker, "Order is not owned by this acceptance run")
    require(order.financial_status == "unpaid" and not order.paid_attempt_id, "Order is not unpaid")
    require(not PaymentAttempt.objects.filter(order=order).exists(), "Order has bank payment history")
    require(not TrialPayment.objects.filter(order=order).exists(), "Order is a trial payment")
    require(
        order.items.exists() and not order.items.exclude(sku__startswith="DEMO-").exists(),
        "Only DEMO items are allowed",
    )


class CheckoutInputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.inside = "checkout-form" in attrs.get("class", "").split()
        if self.inside and tag == "input" and attrs.get("type") == "hidden" and attrs.get("name"):
            self.values[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.inside = False


def new_client():
    from django.conf import settings
    from django.test import Client

    return Client(enforce_csrf_checks=True, HTTP_HOST=settings.SHOP_HOST, HTTP_ORIGIN=settings.SHOP_ORIGIN)


def check_access(order, owner):
    from django.conf import settings
    from apps.orders.notifications import build_notification_email

    path = order.get_absolute_url()
    require(owner.get(path, secure=True).status_code == 200, "Owner cannot view order")
    require(new_client().get(path, secure=True).status_code == 404, "Anonymous UUID access was not denied")
    notice = order.notifications.get(event="created", audience="customer")
    email = build_notification_email(notice)
    prefix = settings.SHOP_ORIGIN.rstrip("/") + path + "access/?token="
    links = [line.strip() for line in email.body.splitlines() if line.strip().startswith(prefix)]
    require(len(links) == 1, "Customer email lacks exactly one order-access link")
    url = urlsplit(links[0])
    other = new_client()
    bad = other.get(url.path, {"token": "invalid-acceptance-token"}, secure=True)
    require(bad.status_code == 410, "Invalid email link was not denied")
    response = other.get(url.path + "?" + url.query, secure=True)
    require(response.status_code == 302 and response["Location"] == path, "Email access did not redirect")
    require("no-store" in response.get("Cache-Control", ""), "Access response must not be cached")
    require(response.get("Referrer-Policy") == "no-referrer", "Access link could leak via referrer")
    require(other.get(path, secure=True).status_code == 200, "Email did not grant access to new session")


def create_check(buyer_email, run_id):
    from django.core.validators import validate_email
    from django.db import connection, transaction
    from django.db.models import F
    from django.test import override_settings
    from apps.catalog.models import Product
    from apps.orders.models import DeliveryMethod, Order
    from apps.orders.notifications import manager_email

    validate_modes()
    buyer_email = buyer_email.strip()
    validate_email(buyer_email)
    require(buyer_email.casefold() != manager_email().casefold(), "Use a separate customer mailbox")
    key, marker = identifiers(run_id)
    with (
        transaction.atomic(),
        override_settings(PAYMENT_STUB_ENABLED=False, CDEK_ENABLED=False, CDEK_DEMO_QUOTES_ENABLED=False),
    ):
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                cursor.execute("SET LOCAL statement_timeout = '15s'")
        existing = Order.objects.select_for_update().filter(checkout_key=key).first()
        if existing:
            validate_order(existing, marker)
            require(
                existing.email.casefold() == buyer_email.casefold(), "Run already belongs to another mailbox"
            )
            return existing.pk, False
        product = (
            Product.objects.select_for_update()
            .filter(
                status="published",
                purchasable=True,
                sku__startswith="DEMO-",
                price__gt=0,
                stock__gt=F("reserved_stock"),
            )
            .order_by("pk")
            .first()
        )
        require(product is not None, "No available DEMO product; nothing changed")
        stock, reserved = product.stock, product.reserved_stock
        delivery_before = list(DeliveryMethod.objects.order_by("pk").values())
        method = DeliveryMethod.objects.create(
            name="Проверка неоплаченного заказа — без отправки",
            slug="qa-" + str(key),
            type="static",
            price="0.00",
            address_required=False,
            active=True,
            is_default=False,
        )
        client = new_client()
        require(
            client.get(f"/products/{product.slug}/", secure=True).status_code == 200,
            "Product page unavailable",
        )
        from django.conf import settings

        csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
        added = client.post(
            f"/cart/add/{product.pk}/", {"quantity": 1, "csrfmiddlewaretoken": csrf}, secure=True
        )
        require(added.status_code == 302, "Cart addition failed")
        page = client.get("/checkout/", secure=True)
        require(page.status_code == 200, "Checkout page unavailable")
        parser = CheckoutInputs()
        parser.feed(page.content.decode())
        require(bool(parser.values.get("quote_token")), "Missing signed checkout quote")
        data = {
            **parser.values,
            "checkout_key": str(key),
            "first_name": "Проверка",
            "last_name": "Заказ",
            "phone_country": "RU",
            "phone": "9990000000",
            "email": buyer_email,
            "delivery_method": str(method.pk),
            "confirmed_delivery": str(method.pk),
            "accept_terms": "on",
            "comment": marker,
            "total": "0.01",
        }
        rejected = client.post("/checkout/", {**data, "csrfmiddlewaretoken": ""}, secure=True)
        require(rejected.status_code == 403, "Checkout without CSRF was not denied")
        require(not Order.objects.filter(checkout_key=key).exists(), "Rejected request created an order")
        first = client.post("/checkout/", data, secure=True)
        require(first.status_code == 302, f"Checkout POST failed: HTTP {first.status_code}")
        order = Order.objects.get(checkout_key=key)
        require(first["Location"] == order.get_absolute_url(), "Unexpected checkout redirect")
        validate_order(order, marker)
        require(
            order.status == "new" and order.total == product.price, "Incorrect unpaid order or server price"
        )
        require(order.delivery_price == 0 and order.items.count() == 1, "Incorrect order composition")
        again = client.post("/checkout/", data, secure=True)
        require(
            again.status_code == 302 and again["Location"] == order.get_absolute_url(), "Repeated POST failed"
        )
        require(Order.objects.filter(checkout_key=key).count() == 1, "Duplicate order")
        product.refresh_from_db()
        require(
            product.stock == stock and product.reserved_stock == reserved + 1, "Incorrect stock reservation"
        )
        require(
            order.reservations.filter(state="active", quantity=1).count() == 1, "Incorrect reservation rows"
        )
        require(
            order.notifications.filter(event="created").count() == 2, "Expected two creation notifications"
        )
        check_access(order, client)
        # PostgreSQL readers never see this method: INSERT and DELETE share one transaction.
        method.delete()
        require(
            list(DeliveryMethod.objects.order_by("pk").values()) == delivery_before,
            "Public delivery methods changed",
        )
        return order.pk, True


def status_check(run_id):
    from apps.catalog.models import Product
    from apps.orders.models import Order

    key, marker = identifiers(run_id)
    order = Order.objects.get(checkout_key=key)
    validate_order(order, marker)
    return {
        "order_id": str(order.public_id),
        "status": order.status,
        "payment": order.financial_status,
        "total": str(order.total),
        "test_mode": order.test_mode,
        "products": list(
            Product.objects.filter(pk__in=order.items.values("product_id")).values(
                "sku", "stock", "reserved_stock"
            )
        ),
        "reservations": list(order.reservations.values("state", "quantity", "expires_at")),
        "notifications": list(
            order.notifications.order_by("pk").values(
                "event", "audience", "attempts", "sent_at", "last_error"
            )
        ),
    }


def cancel_check(run_id):
    from django.db import transaction
    from apps.orders.models import Order
    from apps.orders.services import transition_order

    validate_modes()
    key, marker = identifiers(run_id)
    with transaction.atomic():
        order = Order.objects.select_for_update().get(checkout_key=key)
        validate_order(order, marker)
        transition_order(order.pk, "canceled")
        require(
            not order.reservations.filter(state="active").exists(), "Cancellation did not release reservation"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "status", "cancel"])
    parser.add_argument("--run-id", default="unpaid-20261004")
    args = parser.parse_args()
    try:
        require((Path.cwd() / "manage.py").is_file(), "Run from the installed application directory")
        sys.path.insert(0, str(Path.cwd()))
        import django

        django.setup()
        from django.conf import settings
        from django.db import connection

        require(connection.vendor == "postgresql", "VPS acceptance requires PostgreSQL")
        require(settings.SHOP_ORIGIN.rstrip("/") == "https://shop.dari-sinergii.ru", "Unexpected shop origin")
        result = {}
        if args.action == "create":
            _, created = create_check(os.environ.get("DARI_QA_BUYER_EMAIL", ""), args.run_id)
            result["created_now"] = created
        elif args.action == "cancel":
            cancel_check(args.run_id)
        result.update(status_check(args.run_id))
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        print("UNPAID_ORDER_CHECK_OK")
    except Exception as exc:
        detail = str(exc) if isinstance(exc, CheckFailed) else type(exc).__name__
        print("UNPAID_ORDER_CHECK_STOPPED: " + detail, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
