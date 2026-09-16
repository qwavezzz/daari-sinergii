"""Order email content and settings; transport credentials stay outside the database."""

from email.utils import parseaddr

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.template.loader import render_to_string
from django.urls import reverse

from .models import Notification, NotificationSettings


def manager_email():
    config = NotificationSettings.objects.filter(pk=1).first()
    return ((config.manager_email if config else "") or settings.MANAGER_EMAIL).strip()


def reply_to_email():
    config = NotificationSettings.objects.filter(pk=1).first()
    return (
        (config.reply_to_email if config else "")
        or settings.EMAIL_REPLY_TO
        or manager_email()
        or parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
    ).strip()


def validate_configuration():
    if not settings.DEFAULT_FROM_EMAIL:
        raise ImproperlyConfigured("DEFAULT_FROM_EMAIL не настроен; очередь сохранена.")
    if not manager_email():
        raise ImproperlyConfigured("Укажите email менеджера в админке, в разделе «Почтовые уведомления».")
    for name, value in (
        ("DEFAULT_FROM_EMAIL", settings.DEFAULT_FROM_EMAIL),
        ("Email менеджера", manager_email()),
        ("Email для ответов", reply_to_email()),
    ):
        if not value:
            continue
        try:
            if "\n" in value or "\r" in value:
                raise ValidationError("newline")
            validate_email(parseaddr(value)[1])
        except ValidationError as exc:
            raise ImproperlyConfigured(f"Проверьте {name}; очередь сохранена.") from exc
    if not settings.DEVELOPMENT and settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
        raise ImproperlyConfigured("Для production-уведомлений требуется SMTP backend.")
    if settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend":
        if not settings.EMAIL_HOST:
            raise ImproperlyConfigured("EMAIL_HOST не настроен.")
        if not settings.DEVELOPMENT and not (settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD):
            raise ImproperlyConfigured("Заполните EMAIL_HOST_USER и EMAIL_HOST_PASSWORD на сервере.")
        if settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL:
            raise ImproperlyConfigured("Выберите только один режим: EMAIL_USE_TLS или EMAIL_USE_SSL.")
        if not settings.DEVELOPMENT and not (settings.EMAIL_USE_TLS or settings.EMAIL_USE_SSL):
            raise ImproperlyConfigured("Для production SMTP включите TLS или SSL.")
        if not settings.EMAIL_TIMEOUT or settings.EMAIL_TIMEOUT <= 0:
            raise ImproperlyConfigured("EMAIL_TIMEOUT должен быть больше нуля.")


EVENTS = {
    "created": ("Заказ создан", "Мы получили ваш заказ. Его состав и способ получения указаны ниже."),
    "paid": ("Оплата подтверждена", "Получено подтверждение оплаты вашего заказа."),
    "processing": ("Заказ в обработке", "Мы приступили к обработке вашего заказа."),
    "ready": (
        "Заказ передан в доставку / готов к выдаче",
        "Заказ передан в доставку или подготовлен к выдаче согласно выбранному способу получения. "
        "Подробности можно уточнить, ответив на это письмо.",
    ),
    "completed": ("Заказ завершён", "Заказ завершён. Спасибо, что выбрали «Дары Синергии»."),
    "canceled": ("Заказ отменён", "Заказ отменён. Если у вас остались вопросы, ответьте на это письмо."),
    "refunded": ("Возврат подтверждён", "Подтверждён возврат средств. Срок зачисления зависит от банка."),
}


def build_notification_email(notice):
    order = notice.order
    is_manager = notice.audience == Notification.Audience.MANAGER
    title, description = EVENTS.get(
        notice.event, ("Обновление заказа", "Информация о вашем заказе обновлена.")
    )
    if notice.event.startswith("refund-"):
        title = "Частичный возврат подтверждён"
        description = "Подтверждён возврат части средств. Срок зачисления зависит от банка."
    if is_manager:
        description = "Откройте заказ в админке для просмотра актуального состояния и дальнейшей обработки."
    order_url = settings.SHOP_ORIGIN.rstrip("/") + (
        reverse("admin:orders_order_change", args=[order.pk], urlconf="config.shop_urls")
        if is_manager
        else order.get_absolute_url()
    )
    reply_to = reply_to_email()
    context = {
        "order": order,
        "items": list(order.items.all()),
        "title": title,
        "description": description,
        "is_manager": is_manager,
        "order_url": order_url,
        "link_label": "Открыть заказ в админке" if is_manager else "Посмотреть заказ",
        "reply_to": reply_to,
        "refund_amount": notice.payload.get("refund_amount"),
        "refunded_total": notice.payload.get("refunded_total"),
    }
    email = EmailMultiAlternatives(
        subject=f"{title} · {str(order.public_id)[:8].upper()} — Дары Синергии",
        body=render_to_string("emails/order_notification.txt", context).strip(),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[notice.recipient],
        reply_to=[reply_to] if reply_to else [],
        headers={"Message-ID": f"<dari-order-notice-{notice.pk}@{settings.SHOP_HOST}>"},
    )
    email.attach_alternative(render_to_string("emails/order_notification.html", context), "text/html")
    return email
