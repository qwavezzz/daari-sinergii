from django.db import models


class PublicationStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    PUBLISHED = "published", "Опубликован"
    ARCHIVED = "archived", "Архив"


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        abstract = True


class RateLimitBucket(models.Model):
    key = models.CharField(max_length=128, unique=True)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)


class AuditEntry(models.Model):
    created_at = models.DateTimeField("Время", auto_now_add=True)
    kind = models.CharField("Событие", max_length=80)
    object_id = models.CharField("Объект", max_length=80)
    message = models.TextField("Описание")

    class Meta:
        verbose_name = "Системное событие"
        verbose_name_plural = "Системные события"
        ordering = ["-created_at"]


class WorkerHeartbeat(models.Model):
    name = models.CharField(max_length=40, unique=True)
    finished_at = models.DateTimeField()
    failures = models.PositiveIntegerField(default=0)


class StoreAcceptance(models.Model):
    class Check(models.TextChoices):
        CATALOG = "catalog", "Реальный ассортимент и сведения продавца"
        SHIPPING = "shipping", "Расчёт СДЭК сверён с накладной"
        EMAIL = "email", "Письма получены покупателем и компанией"
        CHECKOUT = "checkout", "Оформление проверено на опубликованном магазине"
        PAYMENT = "payment", "Банковская оплата и возврат проверены"
        FISCAL = "fiscal", "Чеки оплаты, передачи и возврата проверены"
        OPERATIONS = "operations", "Таймеры, оповещения и восстановление проверены"

    kind = models.CharField("Проверка", max_length=20, choices=Check, unique=True)
    reference = models.TextField(
        "Протокол проверки",
        help_text="Дата, среда, ответственный и ссылка/номер протокола с результатом. Без ключей и данных покупателей.",
    )
    confirmed_at = models.DateTimeField("Подтверждено", auto_now=True)
    configuration_digest = models.CharField(max_length=64, editable=False)

    class Meta:
        verbose_name = "Приёмка магазина"
        verbose_name_plural = "Приёмка магазина"

    def __str__(self):
        return self.get_kind_display()
