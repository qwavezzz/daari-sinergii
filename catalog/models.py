import uuid
from pathlib import Path
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from core.models import PublicationStatus, TimeStampedModel
from .storage import product_image_storage


def product_image_path(instance, filename):
    return f"products/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


def validate_image(upload):
    from content.uploads import validate_image as validate_content_image

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
    vat_code = models.PositiveSmallIntegerField("Ставка НДС ЮKassa", null=True, blank=True)
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
