from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from orders.models import Notification


class Command(BaseCommand):
    help = "Повторить неотправленные email из устойчивой очереди. Запускать под flock."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if not settings.DEFAULT_FROM_EMAIL:
            raise CommandError("DEFAULT_FROM_EMAIL не настроен; очередь сохранена.")
        ids = list(
            Notification.objects.filter(sent_at__isnull=True)
            .order_by("pk")
            .values_list("pk", flat=True)[: options["limit"]]
        )
        sent = 0
        for notification_id in ids:
            # Single short email transaction is independent of order/payment transactions.
            with transaction.atomic():
                notice = (
                    Notification.objects.select_for_update().select_related("order").get(pk=notification_id)
                )
                if notice.sent_at:
                    continue
                notice.attempts += 1
                try:
                    labels = {
                        "created": "Заказ создан",
                        "paid": "Оплата подтверждена",
                        "refunded": "Возврат подтверждён",
                    }
                    label = labels.get(notice.event, "Обновление заказа")
                    email = EmailMessage(
                        f"{label} — Дары Синергии",
                        f"{label}. Номер: {notice.order.public_id}.\nСумма: {notice.order.total} ₽.\n"
                        + "Откройте заказ в том браузере, где он был оформлен:\n"
                        + settings.SHOP_ORIGIN
                        + notice.order.get_absolute_url(),
                        settings.DEFAULT_FROM_EMAIL,
                        [notice.recipient],
                        headers={"Message-ID": f"<dari-order-notice-{notice.pk}@{settings.SHOP_HOST}>"},
                    )
                    email.send(fail_silently=False)
                except Exception as exc:
                    notice.last_error = type(exc).__name__[:160]
                else:
                    notice.sent_at = timezone.now()
                    notice.last_error = ""
                    sent += 1
                notice.save(update_fields=["attempts", "sent_at", "last_error"])
        self.stdout.write(f"Отправлено: {sent}.")
