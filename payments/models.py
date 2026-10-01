import uuid
from django.db import models
from django.urls import reverse
from core.models import TimeStampedModel


class TrialPayment(TimeStampedModel):
    """Permanent rehearsal marker, deliberately outside the bank payment ledger."""

    class State(models.TextChoices):
        PENDING = "pending", "Проба ожидает завершения"
        SUCCEEDED = "succeeded", "Проба завершена успешно"
        CANCELED = "canceled", "Проба отменена"

    order = models.OneToOneField(
        "orders.Order", on_delete=models.PROTECT, related_name="trial_payment", editable=False
    )
    state = models.CharField("Результат пробы", max_length=16, choices=State, default=State.PENDING)
    action_key = models.UUIDField(default=uuid.uuid4, editable=False)
    snapshot = models.JSONField("Сохранённый заказ для пробы", editable=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Пробная оплата без списания"
        verbose_name_plural = "Пробные оплаты без списания"

    def get_absolute_url(self):
        return reverse(
            "payments:trial", kwargs={"public_id": self.order.public_id}, urlconf="config.shop_urls"
        )


class PaymentAttempt(TimeStampedModel):
    class State(models.TextChoices):
        CREATING = "creating", "Создаётся"
        UNKNOWN = "unknown", "Требуется сверка"
        PENDING = "pending", "Ожидает оплаты"
        WAITING = "waiting_for_capture", "Ожидает подтверждения"
        SUCCEEDED = "succeeded", "Успешен"
        CANCELED = "canceled", "Отменён"

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payment_attempts")
    provider = models.CharField(
        "Платёжный сервис",
        max_length=16,
        choices=[("legacy", "Архивный сервис"), ("alfabank", "Альфа-Банк")],
        default="alfabank",
        editable=False,
    )
    account_id = models.CharField("Учётная запись магазина", max_length=100, blank=True, editable=False)
    test_mode = models.BooleanField("Тестовая среда", default=True, editable=False)
    idempotence_key = models.UUIDField("Ключ операции", default=uuid.uuid4, unique=True, editable=False)
    provider_id = models.CharField(
        "ID платёжного сервиса", max_length=64, unique=True, null=True, blank=True, editable=False
    )
    amount = models.DecimalField("Сумма", max_digits=12, decimal_places=2)
    currency = models.CharField("Валюта", max_length=3, default="RUB")
    state = models.CharField("Состояние", max_length=24, choices=State, default=State.CREATING, db_index=True)
    confirmation_url = models.URLField("Адрес оплаты", max_length=1000, blank=True)
    request_payload = models.JSONField(default=dict, editable=False)
    last_checked_at = models.DateTimeField("Последняя сверка", null=True, blank=True)
    last_error = models.CharField("Ошибка", max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        constraints = [
            models.UniqueConstraint(
                fields=["order"],
                condition=models.Q(state__in=["creating", "unknown", "pending", "waiting_for_capture"]),
                name="one_active_payment_per_order",
            ),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_amount_positive"),
        ]


class PaymentEvent(models.Model):
    attempt = models.ForeignKey(PaymentAttempt, on_delete=models.PROTECT, related_name="events")
    deduplication_key = models.CharField(max_length=160, unique=True)
    event_type = models.CharField("Событие", max_length=60)
    verified_at = models.DateTimeField("Проверено", auto_now_add=True)

    class Meta:
        verbose_name = "Событие платежа"
        verbose_name_plural = "События платежей"


class Refund(TimeStampedModel):
    attempt = models.ForeignKey(PaymentAttempt, on_delete=models.PROTECT, related_name="refunds")
    provider_id = models.CharField("ID возврата", max_length=64, unique=True)
    amount = models.DecimalField("Сумма", max_digits=12, decimal_places=2)
    currency = models.CharField("Валюта", max_length=3)
    state = models.CharField("Состояние", max_length=20)

    class Meta:
        verbose_name = "Возврат"
        verbose_name_plural = "Возвраты"
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="refund_amount_positive")
        ]
