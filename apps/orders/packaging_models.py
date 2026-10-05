"""Measured packing patterns: fit is attested by a real assembly, never inferred from volume."""

import hashlib
import json
import math
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.core.models import TimeStampedModel


BOX_PHYSICAL_FIELDS = (
    "inner_length_mm",
    "inner_width_mm",
    "inner_height_mm",
    "outer_length_mm",
    "outer_width_mm",
    "outer_height_mm",
    "tare_weight_g",
    "max_weight_g",
)
UNIT_PHYSICAL_FIELDS = ("unit_weight_g", "unit_length_mm", "unit_width_mm", "unit_height_mm")
RECIPE_PHYSICAL_FIELDS = (
    "packing_weight_g",
    "measured_weight_g",
    "outer_length_mm",
    "outer_width_mm",
    "outer_height_mm",
    "instructions",
    "test_only",
)


def measurement_signature(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class PackingBox(TimeStampedModel):
    name = models.CharField("Название коробки", max_length=160)
    code = models.SlugField("Код коробки", unique=True)
    inner_length_mm = models.PositiveIntegerField(
        "Внутренняя длина, мм", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    inner_width_mm = models.PositiveIntegerField(
        "Внутренняя ширина, мм", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    inner_height_mm = models.PositiveIntegerField(
        "Внутренняя высота, мм", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    outer_length_mm = models.PositiveIntegerField(
        "Внешняя длина, мм", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    outer_width_mm = models.PositiveIntegerField(
        "Внешняя ширина, мм", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    outer_height_mm = models.PositiveIntegerField(
        "Внешняя высота, мм", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    tare_weight_g = models.PositiveIntegerField(
        "Вес пустой коробки, г", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    max_weight_g = models.PositiveIntegerField(
        "Предельный вес коробки с содержимым, г", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    active = models.BooleanField("Коробка доступна для сборки", default=True)
    supplier = models.CharField(
        "Источник коробки",
        max_length=12,
        choices=[("cdek", "Покупаем у СДЭК"), ("own", "Другой поставщик"), ("demo", "Учебный пример")],
        default="own",
    )
    source_url = models.URLField("Источник типоразмера", blank=True)
    reference_note = models.TextField(
        "Справочные сведения поставщика",
        blank=True,
        help_text="Ориентир из каталога. Не заменяет замер внутреннего пространства, внешних размеров и тары.",
    )
    auto_enabled = models.BooleanField("Использовать для автоматического подбора", default=False)
    auto_filler_weight_g = models.PositiveIntegerField(
        "Вес общих материалов, скотча и наполнителя, г", default=0
    )
    auto_padding_mm = models.PositiveIntegerField("Защитный отступ от каждой стенки, мм", default=0)
    auto_price_mode = models.CharField(
        "Как учитывать стоимость упаковки",
        max_length=12,
        blank=True,
        default="charge",
        choices=[
            ("", "Выберите способ учёта"),
            ("included", "Учтена в цене товара"),
            ("charge", "Добавлять к доставке"),
        ],
    )
    auto_price = models.DecimalField(
        "Коробка и общие материалы на одно место, ₽",
        max_digits=9,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    auto_test_only = models.BooleanField("Учебная коробка автоподбора", default=False)
    auto_measurement_signature = models.CharField(max_length=64, blank=True, editable=False)
    auto_measured_at = models.DateTimeField(
        "Параметры автоподбора подтверждены", null=True, blank=True, editable=False
    )

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Коробка"
        verbose_name_plural = "Коробки"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(**{f"{field}__gt": 0}), name=f"packingbox_positive_{field}"
            )
            for field in BOX_PHYSICAL_FIELDS
        ] + [
            models.CheckConstraint(
                condition=models.Q(tare_weight_g__lt=models.F("max_weight_g")),
                name="packingbox_tare_below_limit",
            ),
            *[
                models.CheckConstraint(
                    condition=models.Q(**{f"inner_{axis}_mm__lte": models.F(f"outer_{axis}_mm")}),
                    name=f"packingbox_inner_{axis}_fits_outer",
                )
                for axis in ("length", "width", "height")
            ],
        ]

    def clean(self):
        errors = {}
        if self.active or self.auto_enabled:
            for field in BOX_PHYSICAL_FIELDS:
                if type(getattr(self, field)) is not int or getattr(self, field) <= 0:
                    errors[field] = (
                        "Для доступной коробки заполните фактические размеры и вес. Черновик сохраните выключенным."
                    )
        for axis in ("length", "width", "height"):
            inner, outer = getattr(self, f"inner_{axis}_mm"), getattr(self, f"outer_{axis}_mm")
            if inner and outer and inner > outer:
                errors[f"inner_{axis}_mm"] = "Внутренний размер не может превышать внешний."
        if (
            self.tare_weight_g is not None
            and self.max_weight_g is not None
            and self.tare_weight_g >= self.max_weight_g
        ):
            errors["max_weight_g"] = "Предельный вес должен быть больше веса пустой коробки."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        from .auto_profiles import clear_test_confirmation

        clear_test_confirmation(self, "auto", kwargs)
        super().save(*args, **kwargs)

    @property
    def auto_measurements_valid(self):
        from .auto_profiles import valid

        return valid(self, "box")

    def confirm_auto_measurements(self):
        from .auto_profiles import confirm

        confirm(self, "box")

    def __str__(self):
        return self.name


class PackingRecipe(TimeStampedModel):
    name = models.CharField("Название схемы", max_length=160)
    box = models.ForeignKey(
        PackingBox, verbose_name="Коробка", on_delete=models.PROTECT, related_name="recipes"
    )
    packing_weight_g = models.PositiveIntegerField("Вес наполнителя, вставок и скотча, г", default=0)
    measured_weight_g = models.PositiveIntegerField(
        "Измеренный вес готовой посылки, г",
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    outer_length_mm = models.PositiveIntegerField(
        "Измеренная длина посылки, мм", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    outer_width_mm = models.PositiveIntegerField(
        "Измеренная ширина посылки, мм", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    outer_height_mm = models.PositiveIntegerField(
        "Измеренная высота посылки, мм", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    instructions = models.TextField("Как собрать посылку", blank=True)
    active = models.BooleanField("Использовать для расчёта доставки", default=False)
    test_only = models.BooleanField("Учебная схема — только тестовый СДЭК", default=False)
    measurement_signature = models.CharField(max_length=64, blank=True, editable=False)
    measured_at = models.DateTimeField("Сборка и замеры подтверждены", null=True, blank=True, editable=False)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Схема упаковки"
        verbose_name_plural = "Схемы упаковки"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(**{f"{field}__isnull": True}) | models.Q(**{f"{field}__gt": 0}),
                name=f"packingrecipe_positive_{field}",
            )
            for field in ("measured_weight_g", "outer_length_mm", "outer_width_mm", "outer_height_mm")
        ]

    def save(self, *args, **kwargs):
        # Fiction must never acquire or retain an operator's measurement stamp.
        # In particular, toggling this flag back off must not revive an old stamp.
        if self.test_only:
            self.measurement_signature = ""
            self.measured_at = None
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                    "measurement_signature",
                    "measured_at",
                }
        super().save(*args, **kwargs)

    def _measurement_relations(self, *, box=None, rows=None):
        if (box is None) != (rows is None):
            raise ValueError("Supply both box and rows for a loaded measurement snapshot.")
        if box is None:
            # Public model operations must not trust cached relations: changes
            # invalidate confirmation even when an instance was loaded earlier.
            box = PackingBox.objects.get(pk=self.box_id) if self.box_id else None
            rows = self.items.select_related("product").order_by("product_id") if self.pk else []
        elif box.pk != self.box_id:
            raise ValidationError("Коробка в снимке данных не соответствует схеме упаковки.")
        rows = sorted(rows, key=lambda item: item.product_id)
        if any(item.recipe_id != self.pk for item in rows):
            raise ValidationError("Состав в снимке данных не соответствует схеме упаковки.")
        return box, rows

    def measurement_payload(self, *, box=None, rows=None):
        box, rows = self._measurement_relations(box=box, rows=rows)
        return {
            "version": 1,
            "box": {
                "id": box.pk,
                "code": box.code,
                **{field: getattr(box, field) for field in BOX_PHYSICAL_FIELDS},
            }
            if box
            else None,
            **{field: getattr(self, field) for field in RECIPE_PHYSICAL_FIELDS},
            "items": [
                {
                    "product_id": item.product_id,
                    "sku": item.product.sku,
                    "shipping_mode": item.product.shipping_mode,
                    **{field: getattr(item.product, field) for field in UNIT_PHYSICAL_FIELDS},
                    "quantity": item.quantity,
                }
                for item in rows
            ],
        }

    def validate_measurements(self, *, box=None, rows=None):
        """Validate fresh relations, or an explicitly supplied planner snapshot.

        Snapshot callers supply a saved box and recipe items with their product
        relations loaded. No database reads are made in that mode.
        """
        box, rows = self._measurement_relations(box=box, rows=rows)
        if box is None:
            raise ValidationError({"box": "Выберите коробку для схемы упаковки."})
        # The box was fetched above, or came from the caller's loaded snapshot;
        # validating the ForeignKey again would issue one query per recipe.
        self.full_clean(exclude=["box"], validate_unique=False, validate_constraints=False)
        payload = self.measurement_payload(box=box, rows=rows)
        box.full_clean(validate_unique=False, validate_constraints=False)
        errors = []
        if not box.active:
            errors.append("Коробка недоступна для сборки. Включите её или выберите другую.")
        if not self.instructions.strip():
            errors.append(
                "Опишите порядок сборки, положение товаров и защиту, чтобы посылку можно было повторить."
            )
        if not payload["items"]:
            errors.append("Добавьте товары и количество в состав схемы.")
        for field in ("measured_weight_g", "outer_length_mm", "outer_width_mm", "outer_height_mm"):
            if not getattr(self, field):
                errors.append(
                    f"Заполните поле «{self._meta.get_field(field).verbose_name}» после замера готовой посылки."
                )
        contents_weight, total_count = 0, 0
        for row in payload["items"]:
            label = row["sku"]
            if row["shipping_mode"] != "combined":
                errors.append(f"{label}: выберите в товаре упаковку в общую коробку.")
            if not all(isinstance(row[field], int) and row[field] > 0 for field in UNIT_PHYSICAL_FIELDS):
                errors.append(f"{label}: заполните вес и все размеры товара с индивидуальной защитой.")
                continue
            if not 1 <= row["quantity"] <= 100:
                errors.append(f"{label}: количество должно быть от 1 до 100.")
                continue
            contents_weight += row["unit_weight_g"] * row["quantity"]
            total_count += row["quantity"]
        if total_count > 100:
            errors.append("В одной схеме должно быть не больше 100 единиц товара.")
        if self.measured_weight_g:
            # Each stored component and the measured gross are rounded UP to
            # whole grams. For N positive components the discrepancy between
            # sum(ceil(component)) and ceil(sum(component)) is at most N - 1.
            # Count every repeated unit; zero filler introduces no rounding.
            # This is a rounding bound, never a percentage or scale tolerance.
            rounding_allowance_g = total_count + int(self.packing_weight_g > 0)
            minimum_gross_g = (
                contents_weight + box.tare_weight_g + self.packing_weight_g - rounding_allowance_g
            )
            if self.measured_weight_g < minimum_gross_g:
                errors.append(
                    "Измеренный вес посылки меньше суммы веса товаров, коробки и наполнителя "
                    "даже с учётом округления до целых граммов. Проверьте замеры."
                )
            if self.measured_weight_g > box.max_weight_g:
                errors.append("Измеренный вес превышает предельный вес выбранной коробки.")
        outer = [self.outer_length_mm, self.outer_width_mm, self.outer_height_mm]
        if all(outer) and any(
            actual < nominal
            for actual, nominal in zip(
                sorted(outer), sorted([box.outer_length_mm, box.outer_width_mm, box.outer_height_mm])
            )
        ):
            errors.append("Измеренные внешние размеры посылки меньше размеров выбранной коробки.")
        if errors:
            raise ValidationError(errors)
        return payload

    def geometry_notes(self):
        """Bounding boxes cannot prove fit for staggered or diagonal arrangements."""
        payload = self.measurement_payload()
        box = payload["box"]
        if not box:
            return []
        inner = sorted(box[field] for field in ("inner_length_mm", "inner_width_mm", "inner_height_mm"))
        total_volume, notes = 0, []
        for row in payload["items"]:
            dimensions = [row[field] for field in ("unit_length_mm", "unit_width_mm", "unit_height_mm")]
            if not all(dimensions):
                continue
            total_volume += math.prod(dimensions) * row["quantity"]
            if any(item > space for item, space in zip(sorted(dimensions), inner)):
                notes.append(
                    f"{row['sku']}: размеры не подходят для укладки вдоль сторон коробки. Проверьте фактическое положение при сборке и опишите его в инструкции."
                )
        if total_volume > math.prod(inner):
            notes.append(
                "Сумма прямоугольных габаритов товаров больше внутреннего объёма коробки. Для фигурной или шахматной укладки это не доказывает, что товары не поместятся; нужна пробная сборка."
            )
        return notes

    @property
    def measurements_valid(self):
        if self.test_only or not self.measurement_signature or not self.measured_at:
            return False
        try:
            payload = self.validate_measurements()
        except (ValidationError, PackingBox.DoesNotExist):
            return False
        if measurement_signature(payload) != self.measurement_signature or not self.pk:
            return False
        persisted = (
            type(self)
            .objects.filter(pk=self.pk)
            .values(
                *RECIPE_PHYSICAL_FIELDS,
                "box_id",
                "measurement_signature",
                "measured_at",
            )
            .first()
        )
        return bool(
            persisted
            and persisted["measurement_signature"] == self.measurement_signature
            and persisted["measured_at"]
            and persisted["box_id"] == self.box_id
            and all(persisted[field] == getattr(self, field) for field in RECIPE_PHYSICAL_FIELDS)
        )

    def measurements_valid_for_snapshot(self, *, box, rows):
        """Check a planner's freshly loaded snapshot without per-recipe reads.

        Unlike ``measurements_valid``, this deliberately does not re-read the
        persisted recipe. The caller owns loading and checking the complete
        snapshot when pricing or accepting a delivery quote.
        """
        if self.test_only or not self.pk or not self.measurement_signature or not self.measured_at:
            return False
        try:
            payload = self.validate_measurements(box=box, rows=rows)
        except ValidationError:
            return False
        return measurement_signature(payload) == self.measurement_signature

    def confirm_measurements(self):
        """Record an operator's actual trial assembly; never activate implicitly."""
        if self.test_only:
            raise ValidationError(
                "Учебную схему нельзя подтвердить как реальные замеры. "
                "После пробной сборки внесите фактические данные и снимите отметку учебной схемы."
            )
        with transaction.atomic():
            if self.pk:
                type(self).objects.select_for_update().get(pk=self.pk)
            payload = self.validate_measurements()
            self.measurement_signature = measurement_signature(payload)
            self.measured_at = timezone.now()
            self.save(
                update_fields=[
                    *RECIPE_PHYSICAL_FIELDS,
                    "box",
                    "measurement_signature",
                    "measured_at",
                    "updated_at",
                ]
            )

    def __str__(self):
        return self.name


class PackingRecipeItem(models.Model):
    recipe = models.ForeignKey(PackingRecipe, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", verbose_name="Товар / вариант", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(
        "Количество в коробке", validators=[MinValueValidator(1), MaxValueValidator(100)]
    )

    class Meta:
        ordering = ["product_id"]
        verbose_name = "Товар в схеме"
        verbose_name_plural = "Состав коробки"
        constraints = [
            models.UniqueConstraint(fields=["recipe", "product"], name="packingrecipe_unique_product"),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=100),
                name="packingrecipeitem_quantity_range",
            ),
        ]

    def __str__(self):
        return f"{self.product} × {self.quantity}"
