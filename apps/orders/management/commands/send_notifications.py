from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.orders.models import Notification
from apps.orders.notifications import build_notification, smtp_configuration_error


class Command(BaseCommand):
    help = "Повторить неотправленные email из устойчивой очереди. Запускать под flock."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if settings.EMAIL_BACKEND != "django.core.mail.backends.locmem.EmailBackend":
            error = smtp_configuration_error()
            if error:
                raise CommandError(error + " Очередь сохранена.")
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
                    if build_notification(notice).send(fail_silently=False) != 1:
                        raise RuntimeError("Почтовый сервер не принял письмо.")
                except Exception as exc:
                    notice.last_error = type(exc).__name__[:160]
                else:
                    notice.sent_at = timezone.now()
                    notice.last_error = ""
                    sent += 1
                notice.save(update_fields=["attempts", "sent_at", "last_error"])
        self.stdout.write(f"Отправлено: {sent}.")
