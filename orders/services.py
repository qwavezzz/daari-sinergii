from datetime import timedelta
import hashlib
from decimal import Decimal
from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from cart.models import Cart
from catalog.models import Product
from core.models import AuditEntry
from .models import DeliveryMethod, Notification, Order, OrderItem, StockReservation, StoreSettings
from .notifications import manager_email


class QuoteChanged(ValidationError):
    pass


def checkout_is_enabled():
    store = StoreSettings.objects.filter(pk=1).first()
    return bool(
        settings.CHECKOUT_ENABLED
        and store
        and store.checkout_enabled
        and store.terms_text.strip()
        and store.privacy_text.strip()
        and DeliveryMethod.objects.filter(active=True).exists()
    )


def quote_data(cart):
    store = StoreSettings.objects.filter(pk=1).first()
    return {
        "cart": cart.pk,
        "version": cart.version,
        "items": [
            [item.product_id, item.quantity, str(item.product.price)]
            for item in cart.items.select_related("product").order_by("product_id")
        ],
        "delivery": [
            [m.pk, str(m.price), m.name, m.address_required]
            for m in DeliveryMethod.objects.filter(active=True).order_by("pk")
        ],
        "terms": hashlib.sha256(
            ((store.terms_text + "\n" + store.privacy_text) if store else "").encode()
        ).hexdigest(),
    }


def sign_quote(cart):
    return signing.dumps(quote_data(cart), salt="checkout-quote", compress=True)


@transaction.atomic
def checkout_snapshot(cart):
    """Display amounts and confirmation signature describe the same locked snapshot."""
    from cart.services import cart_context

    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    list(Product.objects.select_for_update().filter(pk__in=cart.items.values("product_id")).order_by("pk"))
    list(DeliveryMethod.objects.select_for_update().order_by("pk"))
    list(StoreSettings.objects.select_for_update())
    context = cart_context(cart)
    quote = quote_data(cart)
    context["delivery_quotes"] = {row[0]: Decimal(row[1]) for row in quote["delivery"]}
    return context, signing.dumps(quote, salt="checkout-quote", compress=True)


def queue_notification(order, event, payload=None):
    recipients = [(order.email, Notification.Audience.CUSTOMER)]
    manager = manager_email()
    if manager and manager.casefold() != order.email.casefold():
        recipients.append((manager, Notification.Audience.MANAGER))
    for recipient, audience in recipients:
        Notification.objects.get_or_create(
            order=order,
            event=event,
            recipient=recipient,
            skipped_at__isnull=True,
            defaults={"audience": audience, "payload": payload or {}},
        )


@transaction.atomic
def create_order(cart, data, session_key):
    cart = Cart.objects.select_for_update().get(pk=cart.pk, session_key=session_key)
    existing = Order.objects.filter(checkout_key=data["checkout_key"]).first()
    if existing:
        if existing.session_key != session_key:
            raise ValidationError("Ключ оформления недействителен.")
        return existing
    if not checkout_is_enabled():
        raise ValidationError("Оформление временно недоступно. Условия магазина готовятся к публикации.")
    items = list(cart.items.select_related("product").order_by("product_id"))
    if not items:
        raise ValidationError("Добавьте товары в корзину.")
    locked = {
        p.pk: p
        for p in Product.objects.select_for_update()
        .filter(pk__in=[i.product_id for i in items])
        .order_by("pk")
    }
    method = DeliveryMethod.objects.select_for_update().get(pk=data["delivery_method"].pk)
    store = StoreSettings.objects.select_for_update().get(pk=1)
    if (
        not settings.CHECKOUT_ENABLED
        or not store.checkout_enabled
        or not store.terms_text.strip()
        or not store.privacy_text.strip()
    ):
        raise ValidationError("Оформление временно недоступно. Условия магазина готовятся к публикации.")
    if not method.active or (method.address_required and not data.get("address")):
        raise ValidationError("Проверьте способ получения и адрес.")
    try:
        quoted = signing.loads(data["quote_token"], salt="checkout-quote", max_age=3600)
    except signing.BadSignature as exc:
        raise QuoteChanged(
            "Срок подтверждения истёк. Проверьте актуальную корзину и подтвердите заказ ещё раз."
        ) from exc
    if quoted != quote_data(cart):
        raise QuoteChanged(
            "Цена, состав корзины или условия получения изменились. Проверьте итог и подтвердите заказ ещё раз."
        )
    subtotal = Decimal("0.00")
    for item in items:
        product = locked[item.product_id]
        if not product.is_available or item.quantity > product.available_quantity:
            raise ValidationError(f"«{product.name}» недоступен в выбранном количестве.")
        subtotal += product.price * item.quantity
    order = Order.objects.create(
        checkout_key=data["checkout_key"],
        session_key=session_key,
        name=data["name"],
        phone=data["phone"],
        email=data["email"],
        delivery_method=method.name,
        address=data.get("address", "") if method.address_required else "",
        comment=data.get("comment", ""),
        subtotal=subtotal,
        delivery_price=method.price,
        total=subtotal + method.price,
        terms_accepted_at=timezone.now(),
        terms_snapshot=store.terms_text,
    )
    for item in items:
        product = locked[item.product_id]
        OrderItem.objects.create(
            order=order,
            product=product,
            name=product.name,
            sku=product.sku,
            unit_price=product.price,
            quantity=item.quantity,
            vat_code=product.vat_code,
        )
        product.reserved_stock += item.quantity
        product.save(update_fields=["reserved_stock", "updated_at"])
        StockReservation.objects.create(
            order=order,
            product=product,
            quantity=item.quantity,
            expires_at=timezone.now() + timedelta(minutes=settings.RESERVATION_MINUTES),
        )
    cart.items.all().delete()
    cart.version += 1
    cart.save(update_fields=["version", "updated_at"])
    queue_notification(order, "created")
    AuditEntry.objects.create(
        kind="order.created", object_id=str(order.public_id), message="Создан заказ, товары зарезервированы."
    )
    return order


def release_reservations(order):
    """Caller holds the order lock and has resolved all active/unknown payments."""
    for reservation in order.reservations.select_for_update().filter(state="active").order_by("product_id"):
        product = Product.objects.select_for_update().get(pk=reservation.product_id)
        product.reserved_stock -= reservation.quantity
        product.save(update_fields=["reserved_stock", "updated_at"])
        reservation.state = StockReservation.State.RELEASED
        reservation.save(update_fields=["state", "updated_at"])


def consume_reservations(order):
    """A late success is recorded even when stock needs manual resolution."""
    for reservation in order.reservations.select_for_update().order_by("product_id"):
        if reservation.state == StockReservation.State.CONSUMED:
            continue
        product = Product.objects.select_for_update().get(pk=reservation.product_id)
        if reservation.state == StockReservation.State.ACTIVE:
            product.reserved_stock -= reservation.quantity
            product.stock -= reservation.quantity
        elif product.available_quantity >= reservation.quantity:
            product.stock -= reservation.quantity
        else:
            reservation.state = StockReservation.State.CONFLICT
            reservation.save(update_fields=["state", "updated_at"])
            order.needs_attention = True
            order.attention_reason = (
                "Поздняя оплата: недостаточно товара. Требуется выполнение заказа либо возврат."
            )
            continue
        product.save(update_fields=["stock", "reserved_stock", "updated_at"])
        reservation.state = StockReservation.State.CONSUMED
        reservation.save(update_fields=["state", "updated_at"])


TRANSITIONS = {
    "new": {"processing", "canceled"},
    "processing": {"ready", "canceled"},
    "ready": {"completed", "canceled"},
    "completed": set(),
    "canceled": set(),
}


@transaction.atomic
def transition_order(order_id, target, actor_id=None):
    order = Order.objects.select_for_update().get(pk=order_id)
    if target == order.status:
        return order
    if target not in TRANSITIONS[order.status]:
        raise ValidationError("Этот переход статуса недопустим.")
    if target == Order.Status.CANCELED:
        if order.payment_attempts.exclude(state__in=["canceled", "succeeded"]).exists():
            raise ValidationError("Перед отменой необходимо проверить незавершённый платёж.")
        if order.financial_status in ["paid", "part_refunded"]:
            raise ValidationError("Оплаченный заказ можно отменить после подтверждённого возврата.")
        release_reservations(order)
    if target in {"ready", "completed"} and order.financial_status != "paid":
        raise ValidationError("Перед выполнением требуется подтверждённая оплата.")
    order.status = target
    order.save(update_fields=["status", "updated_at"])
    queue_notification(order, target)
    AuditEntry.objects.create(
        kind="order.status", object_id=str(order.public_id), message=f"Статус {target}; сотрудник {actor_id}"
    )
    return order
