from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from core.models import AuditEntry
from orders.models import Order
from orders.services import consume_reservations, queue_notification, release_reservations
from .models import PaymentAttempt, PaymentEvent, Refund
from .provider import InvalidPayment, PaymentError, PaymentUnavailable, YooKassaClient, safe_provider_id


def payment_payload(order):
    payload = {
        "amount": {"value": str(order.total), "currency": order.currency},
        "capture": True,
        "payment_method_data": {"type": "bank_card"},
        "confirmation": {"type": "redirect", "return_url": settings.SHOP_ORIGIN + order.get_absolute_url()},
        "description": "Заказ " + str(order.public_id),
        "metadata": {"order_id": str(order.public_id)},
    }
    if settings.YOOKASSA_RECEIPT_MODE == "provider":
        items = []
        for item in order.items.all():
            if item.vat_code is None:
                raise PaymentUnavailable("Перед оплатой необходимо настроить налоговые параметры товаров.")
            items.append(
                {
                    "description": item.name[:128],
                    "quantity": str(item.quantity),
                    "amount": {"value": str(item.unit_price), "currency": "RUB"},
                    "vat_code": item.vat_code,
                    "payment_subject": "commodity",
                    "payment_mode": "full_payment",
                }
            )
        if order.delivery_price:
            # Delivery taxation must be explicitly provided; there is no safe inferred rate.
            raise PaymentUnavailable("Для платной доставки требуется согласовать налоговые параметры чека.")
        payload["receipt"] = {"customer": {"email": order.email}, "items": items}
    return payload


def start_payment(order_id, client=None):
    client = client or YooKassaClient()
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.financial_status in {"paid", "part_refunded", "refunded"} or order.status == "canceled":
            raise ValidationError("Оплата этого заказа недоступна.")
        attempt = order.payment_attempts.exclude(state="canceled").first()
        if not attempt:
            if not order.reservations.filter(state="active", expires_at__gt=timezone.now()).exists():
                raise ValidationError("Срок резерва истёк. Оформите заказ заново.")
            attempt = PaymentAttempt.objects.create(
                order=order,
                amount=order.total,
                currency=order.currency,
                request_payload=payment_payload(order),
            )
        order.financial_status = Order.FinancialStatus.PENDING
        order.save(update_fields=["financial_status", "updated_at"])
    # Never hold transaction/stock locks while waiting for the provider.
    if attempt.provider_id:
        return reconcile_attempt(attempt.pk, client)
    if attempt.created_at < timezone.now() - timedelta(hours=23):
        PaymentAttempt.objects.filter(pk=attempt.pk).update(
            state="unknown", last_error="Истёк безопасный срок повтора. Нужна ручная сверка ЮKassa."
        )
        raise PaymentUnavailable("Платёж требует ручной проверки. Новый платёж не создан.")
    try:
        result = client.create_payment(attempt.request_payload, attempt.idempotence_key)
        return apply_payment(attempt.pk, result)
    except PaymentError:
        PaymentAttempt.objects.filter(pk=attempt.pk).exclude(state__in=["succeeded", "canceled"]).update(
            state="unknown", last_error="Неопределённый результат; ожидается сверка."
        )
        raise


def verify_payment(attempt, result):
    if (
        result.id != (attempt.provider_id or result.id)
        or result.amount != attempt.amount
        or result.currency != attempt.currency
        or result.order_id != str(attempt.order.public_id)
        or result.account_id != str(settings.YOOKASSA_SHOP_ID)
        or result.test is not settings.YOOKASSA_TEST_MODE
        or result.status not in {"pending", "waiting_for_capture", "succeeded", "canceled"}
        or (result.status == "succeeded" and not result.paid)
    ):
        raise InvalidPayment("Данные платежа не соответствуют заказу. Требуется проверка.")


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
        deduplication_key=f"payment:{result.id}:{result.status}",
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
            message="Состояние подтверждено авторизованным API ЮKassa.",
        )
    return attempt


def reconcile_attempt(attempt_id, client=None):
    client = client or YooKassaClient()
    attempt = PaymentAttempt.objects.get(pk=attempt_id)
    if not attempt.provider_id:
        return start_payment(attempt.order_id, client)
    result = client.get_payment(attempt.provider_id)
    attempt = apply_payment(attempt.pk, result)
    if attempt.state == "succeeded":
        for refund in client.list_refunds(attempt.provider_id):
            apply_refund(attempt.pk, refund)
    return attempt


@transaction.atomic
def apply_refund(attempt_id, data):
    order_id = PaymentAttempt.objects.values_list("order_id", flat=True).get(pk=attempt_id)
    order = Order.objects.select_for_update().get(pk=order_id)
    attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt_id)
    try:
        refund_id = safe_provider_id(data["id"])
        amount = Decimal(data["amount"]["value"])
        currency = data["amount"]["currency"]
        state = data["status"]
        if (
            data["payment_id"] != attempt.provider_id
            or currency != attempt.currency
            or not amount.is_finite()
            or amount <= 0
            or amount > attempt.amount
            or state not in {"pending", "succeeded", "canceled"}
        ):
            raise InvalidPayment("Возврат не соответствует платежу.")
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise InvalidPayment("Некорректные сведения о возврате.") from exc
    existing = Refund.objects.filter(provider_id=refund_id).first()
    if existing and (
        existing.attempt_id != attempt.pk or existing.amount != amount or existing.currency != currency
    ):
        raise InvalidPayment("Возврат уже зарегистрирован с другими параметрами.")
    if not existing or existing.state != "succeeded":
        Refund.objects.update_or_create(
            provider_id=refund_id,
            defaults={"attempt": attempt, "amount": amount, "currency": currency, "state": state},
        )
    refunded = attempt.refunds.filter(state="succeeded").aggregate(total=Sum("amount"))["total"] or Decimal(
        "0"
    )
    if refunded > attempt.amount:
        raise InvalidPayment("Сумма возвратов превышает сумму платежа.")
    if order.paid_attempt_id == attempt.pk and refunded:
        order.financial_status = "refunded" if refunded == attempt.amount else "part_refunded"
        order.save(update_fields=["financial_status", "updated_at"])
        queue_notification(order, "refunded" if refunded == attempt.amount else f"refund-{refund_id}")
    PaymentEvent.objects.get_or_create(
        deduplication_key=f"refund:{refund_id}:{state}",
        defaults={"attempt": attempt, "event_type": "refund." + state},
    )
    # A refund deliberately does not return physical goods to inventory.
