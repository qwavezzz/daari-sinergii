"""Local checkout rehearsal. Never calls bank, receipt or notification services."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from core.models import AuditEntry
from orders.models import Order
from orders.services import release_reservations
from .models import TrialPayment


def create_trial_payment(order):
    """Called only while creating a new checkout order, inside its transaction.

    Existing orders are never enrolled when visiting or retrying a payment page.
    The marker survives changes to PAYMENT_STUB_ENABLED and blocks bank payment.
    """
    if not getattr(settings, "PAYMENT_STUB_ENABLED", False):
        raise ValidationError("Пробная оплата выключена.")
    if order.financial_status != Order.FinancialStatus.UNPAID or order.payment_attempts.exists():
        raise ValidationError("Банковский заказ нельзя использовать для пробной оплаты.")
    return TrialPayment.objects.create(
        order=order,
        snapshot={
            "items": [
                {
                    "name": item.name,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "subtotal": str(item.subtotal),
                }
                for item in order.items.all()
            ],
            "subtotal": str(order.subtotal),
            "delivery_price": str(order.delivery_price),
            "total": str(order.total),
            "currency": order.currency,
            "delivery_method": order.delivery_method,
            "address": order.address,
            "pickup": order.delivery_snapshot.get("pickup", {}),
        },
    )


@transaction.atomic
def apply_trial_action(order_id, session_key, action, action_key):
    if not getattr(settings, "PAYMENT_STUB_ENABLED", False):
        raise ValidationError("Пробная оплата выключена.")
    if action not in {"success", "cancel", "retry"}:
        raise ValidationError("Выберите завершение, отмену или повтор пробы.")
    # The same lock order is used by the real payment path and stock services.
    order = Order.objects.select_for_update().get(pk=order_id, session_key=session_key)
    trial = TrialPayment.objects.select_for_update().get(order=order)
    if (
        not session_key
        or order.financial_status != Order.FinancialStatus.UNPAID
        or order.paid_attempt_id
        or order.payment_attempts.exists()
        or order.needs_attention
        or order.status != Order.Status.NEW
    ):
        raise ValidationError("Состояние заказа изменилось. Откройте заказ для проверки.")
    # A stale tab, network retry or double click must not override another result.
    if str(trial.action_key) != str(action_key):
        return trial
    if action == "retry" and trial.state == TrialPayment.State.CANCELED:
        trial.state = TrialPayment.State.PENDING
        trial.action_key = uuid.uuid4()
    elif action in {"success", "cancel"} and trial.state == TrialPayment.State.PENDING:
        trial.state = TrialPayment.State.SUCCEEDED if action == "success" else TrialPayment.State.CANCELED
        # Rehearsal never consumes stock. Repeating it only uses the saved snapshot.
        release_reservations(order)
    else:
        return trial
    trial.save(update_fields=["state", "action_key", "updated_at"])
    AuditEntry.objects.create(
        kind="trial_payment." + trial.state,
        object_id=str(order.public_id),
        message="Пробный сценарий без списания денег, кассового чека и отправки заказа.",
    )
    return trial
