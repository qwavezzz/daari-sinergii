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
