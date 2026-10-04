"""Private CLI monitor; intentionally no operational/PII data in public /health/."""

import json
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from apps.core.models import AuditEntry, WorkerHeartbeat
from apps.orders.models import Notification, Order
from apps.payments.models import PaymentAttempt


def operation_report():
    now = timezone.now()
    issues = []
    heartbeats = {row.name: row for row in WorkerHeartbeat.objects.all()}
    for name in ("notifications", "payments"):
        row = heartbeats.get(name)
        if not row or row.finished_at < now - timedelta(seconds=settings.STORE_WORKER_MAX_AGE_SECONDS):
            issues.append(f"worker.{name}.stale")
        elif row.failures:
            issues.append(f"worker.{name}.failures")
    notices = Notification.objects.filter(
        sent_at__isnull=True, skipped_at__isnull=True, order__test_mode=settings.ALFABANK_TEST_MODE
    )
    pending = PaymentAttempt.objects.filter(
        provider="alfabank",
        test_mode=settings.ALFABANK_TEST_MODE,
        state__in=["pending", "unknown", "waiting_for_capture"],
    )
    metrics = {
        "mail_pending": notices.count(),
        "mail_overdue": notices.filter(
            created_at__lt=now - timedelta(seconds=settings.STORE_MAIL_MAX_AGE_SECONDS)
        ).count(),
        "payments_overdue": pending.filter(
            created_at__lt=now - timedelta(seconds=settings.STORE_PAYMENT_MAX_AGE_SECONDS)
        ).count(),
        "payments_unchecked": pending.filter(
            Q(last_checked_at__isnull=True)
            | Q(last_checked_at__lt=now - timedelta(seconds=settings.STORE_WORKER_MAX_AGE_SECONDS))
        )
        .filter(created_at__lt=now - timedelta(seconds=settings.STORE_WORKER_MAX_AGE_SECONDS))
        .count(),
        "orders_attention": Order.objects.filter(
            test_mode=settings.ALFABANK_TEST_MODE, needs_attention=True
        ).count(),
        "shipping_failures_15m": AuditEntry.objects.filter(
            kind="cdek.quote_failed", created_at__gte=now - timedelta(minutes=15)
        ).count(),
    }
    issues.extend(
        key
        for key in ("mail_overdue", "payments_overdue", "payments_unchecked", "orders_attention")
        if metrics[key]
    )
    if metrics["shipping_failures_15m"] >= 3:
        issues.append("shipping_failures_15m")
    return {"healthy": not issues, "issues": issues, "metrics": metrics}


class Command(BaseCommand):
    help = "Проверить фоновые задачи и зависшие операции. --notify отправляет аварийное письмо."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--notify", action="store_true")

    def handle(self, *args, **options):
        report = operation_report()
        if options["notify"] and report["issues"]:
            recent = AuditEntry.objects.filter(
                kind="operations.alert_sent", created_at__gte=timezone.now() - timedelta(minutes=30)
            ).exists()
            if not recent:
                if not settings.OPERATIONS_EMAIL:
                    raise CommandError("Не задан OPERATIONS_EMAIL для аварийных уведомлений.")
                try:
                    count = EmailMessage(
                        "Магазин требует проверки — Дары Синергии",
                        "Диагностика: "
                        + ", ".join(report["issues"])
                        + "\nПроверьте журнал фоновых служб и админку магазина.",
                        settings.DEFAULT_FROM_EMAIL,
                        [settings.OPERATIONS_EMAIL],
                    ).send(fail_silently=False)
                    if count != 1:
                        raise RuntimeError("EmailNotAccepted")
                except Exception as exc:
                    raise CommandError(
                        f"Аварийное письмо не принято: {type(exc).__name__}. Нужен независимый внешний монитор."
                    ) from None
                AuditEntry.objects.create(
                    kind="operations.alert_sent", object_id="", message=", ".join(report["issues"])
                )
        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False))
        else:
            self.stdout.write(
                "Фоновые процессы исправны."
                if report["healthy"]
                else "Требует проверки: " + ", ".join(report["issues"])
            )
        if options["strict"] and not report["healthy"]:
            raise CommandError("Обнаружены незавершённые или неисправные операции.")
