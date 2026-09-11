from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from orders.models import Order
from orders.services import release_reservations
from payments.models import PaymentAttempt
from payments.provider import PaymentError
from payments.services import reconcile_attempt


class Command(BaseCommand):
    help = "Сверить платежи и возвраты, затем освободить только подтверждённо неоплаченные резервы."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument(
            "--refund-days",
            type=int,
            default=0,
            help="Опциональное окно сверки возвратов; 0 проверяет всю историю.",
        )

    def handle(self, *args, **options):
        # Timer uses flock; all state transitions remain safe if two workers overlap.
        candidates = PaymentAttempt.objects.exclude(state="canceled")
        if options["refund_days"] > 0:
            candidates = candidates.filter(
                ~Q(state="succeeded")
                | Q(created_at__gte=timezone.now() - timedelta(days=options["refund_days"]))
            )
        candidates = candidates.order_by(F("last_checked_at").asc(nulls_first=True), "created_at")
        # Reserve part of each bounded batch for refunds, even during a backlog of pending payments.
        pending_limit = max(1, options["limit"] * 4 // 5)
        pending = list(candidates.exclude(state="succeeded")[:pending_limit])
        completed = list(candidates.filter(state="succeeded")[: max(0, options["limit"] - len(pending))])
        checked, failed = 0, 0
        for attempt in pending + completed:
            try:
                reconcile_attempt(attempt.pk)
                checked += 1
            except PaymentError:
                failed += 1
                PaymentAttempt.objects.filter(pk=attempt.pk).update(
                    last_checked_at=timezone.now(),
                    last_error="Автоматическая сверка не завершена; требуется повтор.",
                )
                if not attempt.provider_id and attempt.created_at < timezone.now() - timedelta(hours=23):
                    Order.objects.filter(pk=attempt.order_id).update(
                        needs_attention=True,
                        attention_reason="Платёж не определён дольше срока безопасного повтора. Проверить вручную в ЮKassa; резерв удерживается.",
                    )
        expiring = Order.objects.filter(
            reservations__state="active",
            reservations__expires_at__lte=timezone.now(),
            paid_attempt_id__isnull=True,
        ).distinct()
        released = 0
        for order_id in list(expiring.values_list("pk", flat=True)[: options["limit"]]):
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=order_id)
                if order.paid_attempt_id or order.payment_attempts.exclude(state="canceled").exists():
                    continue
                release_reservations(order)
                order.status = "canceled"
                order.save(update_fields=["status", "updated_at"])
                released += 1
        self.stdout.write(f"Проверено: {checked}; отложено: {failed}; освобождено: {released}.")
