import uuid
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from core.models import TimeStampedModel


class StoreSettings(models.Model):
    checkout_enabled = models.BooleanField("Оформление включено", default=False)
    terms_text = models.TextField("Условия продажи / оферта", blank=True)
    privacy_text = models.TextField("Политика обработки персональных данных", blank=True)
    delivery_text = models.TextField("Условия получения и оплаты", blank=True)

    class Meta:
        verbose_name = "Настройки магазина"
        verbose_name_plural = "Настройки магазина"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Настройки магазина"


class DeliveryMethod(models.Model):
    name = models.CharField("Способ получения", max_length=160)
    slug = models.SlugField("Код", unique=True)
    price = models.DecimalField(
        "Стоимость, ₽", decimal_places=2, max_digits=10, validators=[MinValueValidator(0)]
    )
    address_required = models.BooleanField("Необходим адрес", default=True)
    active = models.BooleanField("Доступен", default=False)
    sort_order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "Способ получения"
        verbose_name_plural = "Способы получения"
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gte=0), name="delivery_price_nonnegative")
        ]

    def __str__(self):
        return self.name


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", "Новый"
        PROCESSING = "processing", "В обработке"
        READY = "ready", "Передан в доставку / готов к выдаче"
        COMPLETED = "completed", "Завершён"
        CANCELED = "canceled", "Отменён"

    class FinancialStatus(models.TextChoices):
        UNPAID = "unpaid", "Не оплачен"
        PENDING = "pending", "Ожидает подтверждения"
        PAID = "paid", "Оплачен"
        PART_REFUNDED = "part_refunded", "Частично возвращён"
        REFUNDED = "refunded", "Возвращён"

    public_id = models.UUIDField("Публичный номер", default=uuid.uuid4, unique=True, editable=False)
    checkout_key = models.UUIDField(unique=True, editable=False)
    session_key = models.CharField(max_length=40, db_index=True, editable=False)
    name = models.CharField("Получатель", max_length=160)
    phone = models.CharField("Телефон", max_length=32)
    email = models.EmailField("Email")
    delivery_method = models.CharField("Способ получения", max_length=160)
    address = models.TextField("Адрес", blank=True)
    comment = models.TextField("Комментарий", blank=True)
    subtotal = models.DecimalField("Стоимость товаров", max_digits=12, decimal_places=2)
    delivery_price = models.DecimalField("Стоимость получения", max_digits=12, decimal_places=2)
    total = models.DecimalField("Итого", max_digits=12, decimal_places=2)
    currency = models.CharField("Валюта", max_length=3, default="RUB", editable=False)
    status = models.CharField("Исполнение", max_length=20, choices=Status, default=Status.NEW)
    financial_status = models.CharField(
        "Оплата", max_length=20, choices=FinancialStatus, default=FinancialStatus.UNPAID, editable=False
    )
    paid_attempt_id = models.PositiveBigIntegerField(null=True, blank=True, editable=False)
    needs_attention = models.BooleanField("Требует внимания", default=False, editable=False)
    attention_reason = models.TextField("Причина", blank=True, editable=False)
    terms_accepted_at = models.DateTimeField("Условия приняты")
    terms_snapshot = models.TextField("Принятые условия", blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        constraints = [
            models.CheckConstraint(condition=models.Q(total__gt=0), name="order_total_positive"),
            models.CheckConstraint(
                condition=models.Q(total=models.F("subtotal") + models.F("delivery_price")),
                name="order_total_matches_components",
            ),
        ]

    def get_absolute_url(self):
        return reverse("orders:detail", kwargs={"public_id": self.public_id}, urlconf="config.shop_urls")

    @property
    def delivery_method_name(self):
        return self.delivery_method

    def __str__(self):
        return str(self.public_id)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="items")
    product = models.ForeignKey("catalog.Product", null=True, on_delete=models.SET_NULL)
    name = models.CharField("Товар", max_length=240)
    sku = models.CharField("Артикул", max_length=80)
    unit_price = models.DecimalField("Цена", max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField("Количество")
    vat_code = models.PositiveSmallIntegerField("Ставка НДС", null=True, blank=True)

    class Meta:
        ordering = ["pk"]
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="order_item_quantity_positive"),
            models.CheckConstraint(condition=models.Q(unit_price__gt=0), name="order_item_price_positive"),
        ]

    @property
    def subtotal(self):
        return self.unit_price * self.quantity


class StockReservation(TimeStampedModel):
    class State(models.TextChoices):
        ACTIVE = "active", "Действует"
        CONSUMED = "consumed", "Списан"
        RELEASED = "released", "Освобождён"
        CONFLICT = "conflict", "Требует проверки"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="reservations")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField("Количество")
    expires_at = models.DateTimeField("Истекает", db_index=True)
    state = models.CharField("Состояние", max_length=12, choices=State, default=State.ACTIVE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order", "product"], name="one_reservation_per_order_product"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="reservation_quantity_positive"),
        ]


class Notification(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="notifications")
    event = models.CharField("Событие", max_length=40)
    recipient = models.EmailField("Получатель")
    sent_at = models.DateTimeField("Отправлено", null=True, blank=True)
    attempts = models.PositiveIntegerField("Попытки", default=0)
    last_error = models.CharField("Ошибка", max_length=160, blank=True)

    class Meta:
        verbose_name = "Email-уведомление"
        verbose_name_plural = "Email-уведомления"
        constraints = [
            models.UniqueConstraint(fields=["order", "event", "recipient"], name="one_order_notification")
        ]
