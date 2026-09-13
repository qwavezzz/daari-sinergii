"""Recipient-specific order mail. No SMTP work happens in an order transaction."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

from .models import Notification


def build_notification(notice):
    order = notice.order
    manager = notice.audience == Notification.Audience.MANAGER
    awaiting_assembly = (
        notice.event == "paid"
        and order.financial_status == "paid"
        and order.status == "new"
        and not order.needs_attention
    )
    if notice.event == "created":
        title = "Поступил новый заказ" if manager else "Ваш заказ оформлен"
        instruction = (
            "Проверьте состав заказа и статус оплаты. Письмо о подтверждённой оплате придёт отдельно."
            if manager
            else "Мы получили ваш заказ. После подтверждения оплаты отправим ещё одно письмо."
        )
    elif notice.event == "paid":
        title = "Заказ оплачен и ожидает сборки" if manager and awaiting_assembly else "Оплата подтверждена"
        instruction = (
            "Откройте заказ и нажмите «Начать сборку»."
            if manager and awaiting_assembly
            else "Откройте заказ и проверьте его текущее состояние."
            if manager
            else "Мы получили подтверждение оплаты вашего заказа. Повторно оплачивать его не нужно."
        )
    else:
        title = "Возврат подтверждён" if notice.event == "refunded" else "Обновление возврата"
        instruction = (
            "Проверьте состояние возврата в заказе." if manager else "Сведения о возврате обновлены."
        )
    if manager and order.needs_attention:
        title = "Оплата получена — заказ требует проверки" if notice.event == "paid" else title
        instruction = "Проверьте причину в заказе перед сборкой или отправкой."
    url = settings.SHOP_ORIGIN + (
        reverse("admin:orders_order_change", args=[order.pk], urlconf="config.shop_urls")
        if manager
        else order.get_absolute_url()
    )
    context = {
        "order": order,
        "items": order.items.all(),
        "manager": manager,
        "title": title,
        "instruction": instruction,
        "order_url": url,
        "test_payment": order.test_mode,
    }
    prefix = "[ТЕСТ] " if context["test_payment"] else ""
    email = EmailMultiAlternatives(
        f"{prefix}{title} — № {order.pk} — Дары Синергии",
        render_to_string("emails/order.txt", context),
        settings.DEFAULT_FROM_EMAIL,
        [notice.recipient],
        headers={"Message-ID": f"<dari-order-notice-{notice.pk}@{settings.SHOP_HOST}>"},
    )
    email.attach_alternative(render_to_string("emails/order.html", context), "text/html")
    return email


def smtp_configuration_error():
    if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
        return "Настроен просмотр писем без реальной отправки. Подключите SMTP."
    if not settings.EMAIL_HOST or not settings.DEFAULT_FROM_EMAIL:
        return "Укажите почтовый сервер и адрес отправителя."
    if settings.EMAIL_USE_SSL and settings.EMAIL_USE_TLS:
        return "Выберите один способ защиты соединения: SSL или STARTTLS."
    if settings.EMAIL_HOST_USER and not settings.EMAIL_HOST_PASSWORD:
        return "Укажите пароль приложения для ящика-отправителя."
    return ""
