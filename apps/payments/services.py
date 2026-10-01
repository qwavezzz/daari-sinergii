from decimal import Decimal
import json
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from apps.content.models import SiteSettings
from apps.core.models import AuditEntry
from apps.orders.models import Order, StoreSettings
from apps.orders.services import consume_reservations, queue_notification, release_reservations
from .models import PaymentAttempt, PaymentEvent, Refund, TrialPayment
from .provider import (
    AlfaBankClient,
    InvalidPayment,
    PaymentError,
    PaymentNotFound,
    PaymentUnavailable,
    minor_units,
    safe_confirmation_url,
)


MISSING_PAYMENT_PAGE = (
    "Платёж найден в банке, но адрес оплаты не получен. Требуется ручная сверка в Альфа-Банке."
)

# Stable internal VAT codes -> bank taxType; these enumerations are not interchangeable.
# Official REST documentation, «Содержимое tax», verified 2026-10-01:
# https://alfabank.ru/sme/payservice/internet-acquiring/docs/connection-options/api/rest/
ALFA_TAX_TYPES = {1: 0, 2: 1, 3: 2, 4: 6, 5: 4, 6: 7, 7: 10, 8: 12, 9: 11, 10: 13, 11: 14, 12: 15}


def require_live_store_details():
    seller = SiteSettings.objects.first()
    store = StoreSettings.objects.first()
    seller_fields = (
        "legal_name",
        "inn",
        "registration_number",
        "email",
        "phone",
        "address",
        "postal_address",
        "return_address",
    )
    if (
        not seller
        or any(not getattr(seller, field).strip() for field in seller_fields)
        or (seller.seller_type == "company" and not seller.kpp.strip())
        or not store
        or any(
            not getattr(store, field).strip()
            for field in (
                "terms_text",
                "privacy_text",
                "delivery_text",
                "returns_text",
            )
        )
    ):
        raise PaymentUnavailable(
            "Перед реальной оплатой необходимо заполнить сведения о продавце и условия покупки."
        )
    try:
        seller.full_clean()
    except ValidationError as exc:
        raise PaymentUnavailable("Сведения о продавце требуют проверки перед реальной оплатой.") from exc


def valid_reservations(order):
    reservations = order.reservations.all()
    return (
        reservations.exists()
        and not reservations.exclude(
            state="active",
            expires_at__gt=timezone.now(),
        ).exists()
    )


def receipt_item(position, name, price, quantity, vat_code, *, service=False):
    if type(vat_code) is not int or vat_code not in ALFA_TAX_TYPES:
        raise PaymentUnavailable("Перед оплатой необходимо настроить налоговые параметры товаров и доставки.")
    return {
        "positionId": str(position),
        "name": name[:128],
        "itemCode": str(position),
        "quantity": {"value": quantity, "measure": "шт"},
        "itemPrice": minor_units(price),
        "itemAmount": minor_units(price * quantity),
        "tax": {"taxType": ALFA_TAX_TYPES[vat_code]},
        "itemAttributes": {
            "attributes": [
                # Goods are ordered before handover: full prepayment, rather than payment on receipt.
                {"name": "paymentMethod", "value": "1"},
                {"name": "paymentObject", "value": "4" if service else "1"},
            ]
        },
    }


def payment_payload(order, key=None):
    if order.currency != "RUB" or not 0 < minor_units(order.total) <= 999999999999:
        raise InvalidPayment("Некорректная сумма или валюта заказа.")
    payload = {
        "amount": minor_units(order.total),
        "currency": 643,
        "returnUrl": settings.SHOP_ORIGIN + order.get_absolute_url(),
        "failUrl": settings.SHOP_ORIGIN + order.get_absolute_url(),
        "description": "Заказ " + str(order.public_id),
        "jsonParams": json.dumps({"order_id": str(order.public_id)}),
        "language": "ru",
        "sessionTimeoutSecs": 1200,
    }
    if key is not None:
        payload["orderNumber"] = str(key)
    if settings.ALFABANK_RECEIPT_MODE == "bank":
        tax_system = settings.ALFABANK_TAX_SYSTEM
        if type(tax_system) is not int or tax_system not in range(6):
            raise PaymentUnavailable("Необходимо согласовать систему налогообложения для чека.")
        items = []
        for index, item in enumerate(order.items.all(), 1):
            items.append(receipt_item(index, item.name, item.unit_price, item.quantity, item.vat_code))
        if order.delivery_price:
            items.append(
                receipt_item(
                    len(items) + 1,
                    "Доставка: " + order.delivery_method,
                    order.delivery_price,
                    1,
                    order.delivery_vat_code,
                    service=True,
                )
            )
        if sum(item["itemAmount"] for item in items) != payload["amount"]:
            raise InvalidPayment("Сумма чека не совпадает с итогом заказа.")
        payload["taxSystem"] = tax_system
        payload["orderBundle"] = json.dumps(
            {
                "customerDetails": {"email": order.email},
                "cartItems": {"items": items},
            },
            ensure_ascii=False,
        )
    return payload


def start_payment(order_id, client=None):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if TrialPayment.objects.filter(order=order).exists():
            raise PaymentUnavailable("Пробный заказ нельзя оплатить в банке. Оформите новый заказ.")
        client = client or AlfaBankClient()
        if order.financial_status in {"paid", "part_refunded", "refunded"} or order.status == "canceled":
            raise ValidationError("Оплата этого заказа недоступна.")
        if order.needs_attention:
            raise PaymentUnavailable("Заказ требует проверки менеджером перед оплатой.")
        if not settings.ALFABANK_TEST_MODE and order.items.filter(sku__startswith="DEMO-").exists():
            raise PaymentUnavailable("Демонстрационные товары недоступны для реальной оплаты.")
        if not settings.ALFABANK_TEST_MODE and order.delivery_type == "cdek_pvz":
            snapshot = order.delivery_snapshot
            if (
                settings.CDEK_TEST_MODE
                or not isinstance(snapshot, dict)
                or snapshot.get("test_mode") is not False
            ):
                raise PaymentUnavailable(
                    "Реальная оплата недоступна для тестового или неподтверждённого расчёта доставки СДЭК."
                )
        if not settings.ALFABANK_TEST_MODE:
            require_live_store_details()
        if order.payment_attempts.filter(provider="legacy").exists():
            raise PaymentUnavailable("Архивный платёж требует ручной сверки. Новый платёж не создан.")
        attempt = order.payment_attempts.exclude(state="canceled").first()
        if not attempt:
            if not valid_reservations(order):
                raise ValidationError("Срок резерва истёк. Оформите заказ заново.")
            key = uuid.uuid4()
            attempt = PaymentAttempt.objects.create(
                order=order,
                provider="alfabank",
                account_id=settings.ALFABANK_USERNAME,
                test_mode=settings.ALFABANK_TEST_MODE,
                idempotence_key=key,
                amount=order.total,
                currency=order.currency,
                request_payload=payment_payload(order, key),
            )
        order.financial_status = Order.FinancialStatus.PENDING
        order.save(update_fields=["financial_status", "updated_at"])
    # Never hold transaction/stock locks while waiting for the provider.
    return reconcile_attempt(attempt.pk, client, allow_registration=True)


def verify_context(attempt):
    if (
        TrialPayment.objects.filter(order_id=attempt.order_id).exists()
        or attempt.provider != "alfabank"
        or attempt.account_id != settings.ALFABANK_USERNAME
        or attempt.test_mode is not settings.ALFABANK_TEST_MODE
    ):
        raise PaymentUnavailable(
            "Платёж относится к другой учётной записи или среде. Требуется ручная сверка."
        )


def reconcile_attempt(attempt_id, client=None, *, allow_registration=False):
    attempt = PaymentAttempt.objects.select_related("order").get(pk=attempt_id)
    verify_context(attempt)
    client = client or AlfaBankClient()
    try:
        if attempt.provider_id:
            result = client.get_payment(attempt.provider_id)
        else:
            try:
                result = client.get_payment(order_number=str(attempt.idempotence_key))
            except PaymentNotFound:
                # Background reconciliation never creates charges. A retry requires an
                # explicit checkout action and the same persisted merchant order number.
                if (
                    not allow_registration
                    or attempt.order.status == "canceled"
                    or not valid_reservations(attempt.order)
                ):
                    raise PaymentUnavailable("Платёж требует проверки. Новый платёж не создан.")
                result = client.create_payment(attempt.request_payload, attempt.idempotence_key)
        return apply_payment(attempt.pk, result)
    except PaymentError:
        PaymentAttempt.objects.filter(pk=attempt.pk).exclude(state__in=["succeeded", "canceled"]).update(
            state="unknown", last_error="Неопределённый результат; ожидается сверка."
        )
        raise


def verify_payment(attempt, result):
    verify_context(attempt)
    if (
        result.id != (attempt.provider_id or result.id)
        or result.amount != attempt.amount
        or result.currency != attempt.currency
        or result.order_id != str(attempt.order.public_id)
        or result.account_id != attempt.account_id
        or result.test is not attempt.test_mode
        or result.order_number != str(attempt.idempotence_key)
        or result.status not in {"pending", "waiting_for_capture", "succeeded", "canceled"}
        or (result.status == "succeeded" and not result.paid)
        or (result.status != "succeeded" and result.paid)
        or minor_units(result.refunded_amount) > minor_units(attempt.amount)
        or (result.status != "succeeded" and result.refunded_amount)
    ):
        raise InvalidPayment("Данные платежа не соответствуют заказу. Требуется проверка.")
    if result.confirmation_url:
        safe_confirmation_url(result.confirmation_url, attempt.test_mode, result.id)


@transaction.atomic
def apply_payment(attempt_id, result):
    order_id = PaymentAttempt.objects.values_list("order_id", flat=True).get(pk=attempt_id)
    order = Order.objects.select_for_update().get(pk=order_id)
    attempt = PaymentAttempt.objects.select_for_update().select_related("order").get(pk=attempt_id)
    verify_payment(attempt, result)
    if PaymentAttempt.objects.filter(provider_id=result.id).exclude(pk=attempt.pk).exists():
        raise InvalidPayment("Платёж уже привязан к другой попытке.")
    attempt.provider_id = result.id
    attempt.confirmation_url = result.confirmation_url or attempt.confirmation_url
    attempt.last_checked_at = timezone.now()
    attempt.last_error = ""
    previous = attempt.state
    # A confirmed success never regresses. A late success after cancellation is handled.
    if previous != "succeeded" and not (previous == "canceled" and result.status != "succeeded"):
        attempt.state = result.status
    if attempt.state in {"pending", "waiting_for_capture"} and not attempt.confirmation_url:
        attempt.last_error = MISSING_PAYMENT_PAGE
        if not order.needs_attention:
            order.needs_attention = True
            order.attention_reason = MISSING_PAYMENT_PAGE
    elif order.attention_reason == MISSING_PAYMENT_PAGE:
        # A concurrent registration response or later terminal status resolves this
        # particular recovery problem without clearing unrelated manager warnings.
        order.needs_attention = False
        order.attention_reason = ""
    attempt.save(
        update_fields=[
            "provider_id",
            "confirmation_url",
            "last_checked_at",
            "last_error",
            "state",
            "updated_at",
        ]
    )
    PaymentEvent.objects.get_or_create(
        deduplication_key=f"alfabank:payment:{result.id}:{result.status}",
        defaults={"attempt": attempt, "event_type": result.status},
    )
    if attempt.state == "succeeded":
        if order.paid_attempt_id and order.paid_attempt_id != attempt.pk:
            order.needs_attention = True
            order.attention_reason = (
                "Повторная успешная оплата другим платежом. Требуется проверка и возврат дублирующей суммы."
            )
        elif not order.paid_attempt_id:
            order.paid_attempt_id = attempt.pk
            order.financial_status = Order.FinancialStatus.PAID
            consume_reservations(order)
            if order.status == "canceled":
                order.needs_attention = True
                order.attention_reason = (
                    "Получена поздняя оплата отменённого заказа. Требуется выполнение либо возврат."
                )
            queue_notification(order, "paid")
    elif attempt.state == "canceled" and not order.paid_attempt_id:
        order.financial_status = Order.FinancialStatus.UNPAID
        # Cancellation closes this order's reserve; a new cart requires fresh confirmation.
        if (
            not order.payment_attempts.exclude(pk=attempt.pk)
            .exclude(state__in=["canceled", "succeeded"])
            .exists()
        ):
            release_reservations(order)
            if order.status != Order.Status.CANCELED:
                queue_notification(order, "canceled")
            order.status = Order.Status.CANCELED
    order.save(
        update_fields=[
            "paid_attempt_id",
            "financial_status",
            "needs_attention",
            "attention_reason",
            "status",
            "updated_at",
        ]
    )
    if previous != attempt.state:
        AuditEntry.objects.create(
            kind="payment." + attempt.state,
            object_id=str(order.public_id),
            message="Состояние подтверждено авторизованным API Альфа-Банка.",
        )
    if result.status == "succeeded":
        apply_refund(attempt.pk, result)
    return attempt


@transaction.atomic
def apply_refund(attempt_id, result):
    """Record only the increase of Alfa's cumulative confirmed refunded amount.

    Synthetic local IDs describe reconciliation deltas, not bank refund IDs.
    Stale/lower snapshots cannot regress a confirmed refund or send another email.
    """
    order_id = PaymentAttempt.objects.values_list("order_id", flat=True).get(pk=attempt_id)
    order = Order.objects.select_for_update().get(pk=order_id)
    attempt = PaymentAttempt.objects.select_for_update().select_related("order").get(pk=attempt_id)
    verify_payment(attempt, result)
    if result.status != "succeeded" or attempt.state != "succeeded":
        raise InvalidPayment("Возврат требует подтверждённого платежа.")
    previous = attempt.refunds.filter(state="succeeded").aggregate(total=Sum("amount"))["total"] or Decimal(
        "0"
    )
    refunded = result.refunded_amount
    if refunded <= previous:
        return
    amount = refunded - previous
    refund_id = f"alfa-{attempt.pk}-{minor_units(refunded)}"
    Refund.objects.create(
        provider_id=refund_id,
        attempt=attempt,
        amount=amount,
        currency=attempt.currency,
        state="succeeded",
    )
    if order.paid_attempt_id == attempt.pk:
        order.financial_status = "refunded" if refunded == attempt.amount else "part_refunded"
        order.save(update_fields=["financial_status", "updated_at"])
        queue_notification(
            order,
            "refunded" if refunded == attempt.amount else f"refund-{refund_id}",
            payload={"refund_amount": str(amount), "refunded_total": str(refunded)},
        )
    PaymentEvent.objects.get_or_create(
        deduplication_key=f"alfabank:refund:{refund_id}",
        defaults={"attempt": attempt, "event_type": "refund.succeeded"},
    )
    # A refund deliberately does not return physical goods to inventory.
