import hashlib
import json
import uuid
from pathlib import Path
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from apps.core.models import PublicationStatus, TimeStampedModel
from .storage import product_image_storage


def product_image_path(instance, filename):
    return f"products/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


def validate_image(upload):
    from apps.content.uploads import validate_image as validate_content_image

    validate_content_image(upload)


class Category(TimeStampedModel):
    name = models.CharField("Название", max_length=160)
    slug = models.SlugField("Адрес", unique=True)
    description = models.TextField("Описание", blank=True)
    active = models.BooleanField("Активна", default=True)
    sort_order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    class ShippingMode(models.TextChoices):
        INDIVIDUAL = "individual", "Отдельная посылка для каждой единицы"
        COMBINED = "combined", "Общая коробка по проверенной схеме"
        AUTOMATIC = "automatic", "Автоматический подбор общей коробки"

    name = models.CharField("Название", max_length=240)
    slug = models.SlugField("Адрес", unique=True, max_length=240)
    sku = models.CharField("Артикул", unique=True, max_length=80)
    categories = models.ManyToManyField(
        Category, verbose_name="Категории", related_name="products", blank=True
    )
    short_description = models.TextField("Краткое описание", blank=True)
    description = models.TextField("Полное описание", blank=True)
    price = models.DecimalField(
        "Цена, ₽",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0.01)],
    )
    status = models.CharField(
        "Публикация", max_length=12, choices=PublicationStatus, default=PublicationStatus.DRAFT, db_index=True
    )
    purchasable = models.BooleanField("Доступен для покупки", default=False)
    stock = models.PositiveIntegerField("Количество на складе", default=0)
    reserved_stock = models.PositiveIntegerField("В резерве", default=0, editable=False)
    vat_code = models.PositiveSmallIntegerField("Код ставки НДС", null=True, blank=True)
    shipping_mode = models.CharField(
        "Как упаковывать",
        max_length=12,
        choices=ShippingMode,
        default=ShippingMode.INDIVIDUAL,
    )
    unit_weight_g = models.PositiveIntegerField(
        "Вес товара с индивидуальной защитой, г",
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    unit_length_mm = models.PositiveIntegerField(
        "Длина товара с защитой, мм",
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    unit_width_mm = models.PositiveIntegerField(
        "Ширина товара с защитой, мм",
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    unit_height_mm = models.PositiveIntegerField(
        "Высота товара с защитой, мм",
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    unit_allow_rotation = models.BooleanField("Разрешено переворачивать товар с защитой", default=False)
    unit_stack_limit_g = models.PositiveIntegerField(
        "Допустимый вес сверху, г",
        default=0,
        help_text="0 — сверху ничего не ставить. Укажите проверенную нагрузку для защищённого товара.",
    )
    unit_packing_group = models.SlugField(
        "Группа совместной упаковки",
        default="general",
        max_length=64,
        help_text="Только товары одной группы объединяются автоматически. Например: cosmetics, equipment.",
    )
    unit_test_only = models.BooleanField("Учебные параметры автоподбора", default=False)
    unit_measurement_signature = models.CharField(max_length=64, blank=True, editable=False)
    unit_measured_at = models.DateTimeField(
        "Параметры автоподбора подтверждены", null=True, blank=True, editable=False
    )
    package_weight_g = models.PositiveIntegerField(
        "Вес одного упакованного товара, г", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    package_length_cm = models.PositiveIntegerField(
        "Длина упаковки, см", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    package_width_cm = models.PositiveIntegerField(
        "Ширина упаковки, см", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    package_height_cm = models.PositiveIntegerField(
        "Высота упаковки, см", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    package_measurement_signature = models.CharField(max_length=64, blank=True, editable=False)
    package_measured_at = models.DateTimeField(
        "Замеры отдельной посылки подтверждены", null=True, blank=True, editable=False
    )
    sort_order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gt=0) | models.Q(price__isnull=True), name="product_positive_price"
            ),
            models.CheckConstraint(
                condition=models.Q(reserved_stock__lte=models.F("stock")), name="stock_covers_reservations"
            ),
            models.CheckConstraint(
                condition=models.Q(purchasable=False) | models.Q(price__isnull=False),
                name="purchasable_has_price",
            ),
        ]

    @property
    def available_quantity(self):
        return self.stock - self.reserved_stock

    def save(self, *args, **kwargs):
        from apps.orders.auto_profiles import clear_test_confirmation

        clear_test_confirmation(self, "unit", kwargs)
        super().save(*args, **kwargs)

    @property
    def auto_measurements_valid(self):
        from apps.orders.auto_profiles import valid

        return valid(self, "unit")

    def confirm_auto_measurements(self):
        from apps.orders.auto_profiles import confirm

        confirm(self, "unit")

    def package_measurement_payload(self):
        return {
            field: getattr(self, field)
            for field in ("package_weight_g", "package_length_cm", "package_width_cm", "package_height_cm")
        }

    def validate_package_measurements(self):
        errors = {
            field: "Измерьте готовую закрытую посылку и укажите целое положительное значение."
            for field, value in self.package_measurement_payload().items()
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0
        }
        if self.shipping_mode != self.ShippingMode.INDIVIDUAL:
            errors["shipping_mode"] = "Для общей коробки подтвердите замеры в схеме упаковки."
        if errors:
            raise ValidationError(errors)

    def _package_signature(self):
        return hashlib.sha256(
            json.dumps(self.package_measurement_payload(), sort_keys=True).encode()
        ).hexdigest()

    @property
    def package_measurements_valid(self):
        if not self.package_measurement_signature or not self.package_measured_at:
            return False
        try:
            self.validate_package_measurements()
        except ValidationError:
            return False
        if self.package_measurement_signature != self._package_signature() or not self.pk:
            return False
        physical = self.package_measurement_payload()
        persisted = (
            type(self)
            .objects.filter(pk=self.pk)
            .values(
                *physical,
                "shipping_mode",
                "package_measurement_signature",
                "package_measured_at",
            )
            .first()
        )
        return bool(
            persisted
            and persisted["package_measurement_signature"] == self.package_measurement_signature
            and persisted["package_measured_at"]
            and persisted["shipping_mode"] == self.ShippingMode.INDIVIDUAL
            and all(persisted[field] == value for field, value in physical.items())
        )

    def confirm_package_measurements(self):
        """Explicit operator attestation; ordinary saves never verify measurements."""
        self.validate_package_measurements()
        self.package_measurement_signature = self._package_signature()
        self.package_measured_at = timezone.now()
        self.save(
            update_fields=[
                *self.package_measurement_payload(),
                "package_measurement_signature",
                "package_measured_at",
                "updated_at",
            ]
        )

    @property
    def is_available(self):
        return (
            self.status == PublicationStatus.PUBLISHED
            and self.purchasable
            and self.price is not None
            and self.available_quantity > 0
        )

    @property
    def image_url(self):
        image = self.images.first()
        return image.image.url if image else ""

    @property
    def specifications(self):
        return self.attributes

    def get_absolute_url(self):
        return reverse("catalog:product", kwargs={"slug": self.slug}, urlconf="config.shop_urls")

    def clean(self):
        if self.purchasable and not self.price:
            raise ValidationError({"price": "Укажите подтверждённую цену перед включением покупки."})
        if self.reserved_stock > self.stock:
            raise ValidationError({"stock": "Остаток не может быть меньше действующих резервов."})

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(
        "Изображение",
        upload_to=product_image_path,
        validators=[validate_image],
        storage=product_image_storage,
    )
    alt = models.CharField("Описание изображения", max_length=240)
    sort_order = models.PositiveIntegerField("Порядок", default=0)

    @property
    def alt_text(self):
        return self.alt

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "Изображение товара"
        verbose_name_plural = "Изображения товаров"


class ProductAttribute(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField("Характеристика", max_length=160)
    value = models.CharField("Значение", max_length=500)
    sort_order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "Характеристика"
        verbose_name_plural = "Характеристики"
