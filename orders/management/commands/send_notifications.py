from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from orders.models import Notification
from orders.notifications import build_notification_email, manager_email, validate_configuration


class Command(BaseCommand):
    help = "Отправить готовые письма очереди. Запускать под flock. --check не отправляет писем."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--check", action="store_true")

    def handle(self, *args, **options):
        try:
            validate_configuration()
        except ImproperlyConfigured as exc:
            raise CommandError(str(exc)) from None
        if options["check"]:
            self.stdout.write("Настройки заполнены. Соединение с SMTP и доставка ещё не проверены.")
            return
        if options["limit"] < 1:
            raise CommandError("--limit должен быть больше нуля.")
        ids = list(
            Notification.objects.filter(
                sent_at__isnull=True,
                skipped_at__isnull=True,
                next_attempt_at__lte=timezone.now(),
            )
            .order_by("next_attempt_at", "pk")
            .values_list("pk", flat=True)[: options["limit"]]
        )
        sent = failed = 0
        for notification_id in ids:
            with transaction.atomic():
                # Lock only this queue row, not the joined order, during SMTP.
                notice = (
                    Notification.objects.select_for_update(of=("self",))
                    .select_related("order")
                    .get(pk=notification_id)
                )
                if notice.sent_at or notice.skipped_at or notice.next_attempt_at > timezone.now():
                    continue
                notice.attempts += 1
                try:
                    if notice.audience == Notification.Audience.MANAGER:
                        recipient = manager_email()
                        if not recipient:
                            raise ImproperlyConfigured("ManagerEmailMissing")
                        if recipient != notice.recipient:
                            duplicate = (
                                Notification.objects.filter(
                                    order=notice.order,
                                    event=notice.event,
                                    recipient=recipient,
                                    skipped_at__isnull=True,
                                )
                                .exclude(pk=notice.pk)
                                .exists()
                            )
                            if duplicate:
                                notice.skipped_at = timezone.now()
                                notice.last_error = "AlreadyQueuedForRecipient"
                                notice.save(update_fields=["skipped_at", "last_error", "attempts"])
                                continue
                            notice.recipient = recipient
                    if build_notification_email(notice).send(fail_silently=False) != 1:
                        raise RuntimeError("EmailNotAccepted")
                except Exception as exc:
                    notice.last_error = type(exc).__name__[:160]
                    delay = min(60 * 2 ** min(notice.attempts - 1, 6), 3600)
                    notice.next_attempt_at = timezone.now() + timedelta(seconds=delay)
                    failed += 1
                else:
                    notice.sent_at = timezone.now()
                    notice.last_error = ""
                    sent += 1
                notice.save(
                    update_fields=["recipient", "attempts", "sent_at", "last_error", "next_attempt_at"]
                )
        self.stdout.write(f"Отправлено: {sent}; отложено после ошибки: {failed}.")
