"""Explicit verification of inputs used by the automatic packing planner."""

import hashlib
import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone


UNIT_FIELDS = (
    "shipping_mode",
    "unit_weight_g",
    "unit_length_mm",
    "unit_width_mm",
    "unit_height_mm",
    "unit_allow_rotation",
    "unit_stack_limit_g",
    "unit_packing_group",
    "unit_test_only",
)
BOX_FIELDS = (
    "inner_length_mm",
    "inner_width_mm",
    "inner_height_mm",
    "outer_length_mm",
    "outer_width_mm",
    "outer_height_mm",
    "tare_weight_g",
    "max_weight_g",
    "auto_filler_weight_g",
    "auto_padding_mm",
    "auto_test_only",
    "auto_price_mode",
    "auto_price",
)


def payload(obj, kind):
    fields = UNIT_FIELDS if kind == "unit" else BOX_FIELDS
    return {
        "version": 1,
        "id": obj.pk,
        **{
            field: (format(value, ".2f") if isinstance(value, Decimal) else value)
            for field in fields
            for value in [getattr(obj, field)]
        },
    }


def signature(obj, kind):
    return hashlib.sha256(json.dumps(payload(obj, kind), sort_keys=True, default=str).encode()).hexdigest()


def validate(obj, kind):
    if kind == "unit":
        fields = ("unit_weight_g", "unit_length_mm", "unit_width_mm", "unit_height_mm")
        if obj.shipping_mode != "automatic":
            raise ValidationError("Выберите автоматический подбор коробки в способе упаковки товара.")
        if not isinstance(obj.unit_packing_group, str) or not obj.unit_packing_group.strip():
            raise ValidationError("Укажите группу совместной упаковки товара.")
        if type(obj.unit_stack_limit_g) is not int or obj.unit_stack_limit_g < 0:
            raise ValidationError("Допустимая нагрузка сверху должна быть неотрицательным целым числом.")
    else:
        fields = BOX_FIELDS[:8]
    if any(type(getattr(obj, f)) is not int or getattr(obj, f) <= 0 for f in fields):
        raise ValidationError("Заполните положительные вес и все размеры после фактических замеров.")
    if kind == "box":
        obj.clean()
        if obj.auto_price_mode not in {"included", "charge"}:
            raise ValidationError(
                "Выберите, включена ли стоимость упаковки в товар или добавляется к доставке."
            )
        if obj.auto_price_mode == "charge" and (
            not isinstance(obj.auto_price, Decimal)
            or not obj.auto_price.is_finite()
            or not Decimal("0") <= obj.auto_price <= Decimal("9999999.99")
            or obj.auto_price != obj.auto_price.quantize(Decimal("0.01"))
        ):
            raise ValidationError("Укажите проверенную стоимость коробки и материалов в рублях с копейками.")
        for f in ("auto_filler_weight_g", "auto_padding_mm"):
            if type(getattr(obj, f)) is not int or getattr(obj, f) < 0:
                raise ValidationError("Вес материалов и отступ от стенок должны быть неотрицательными.")
        if obj.tare_weight_g + obj.auto_filler_weight_g >= obj.max_weight_g:
            raise ValidationError("После добавления тары и материалов должен оставаться запас по весу.")
        if any(
            getattr(obj, f"inner_{axis}_mm") <= 2 * obj.auto_padding_mm
            for axis in ("length", "width", "height")
        ):
            raise ValidationError("Отступ от стенок занимает всё внутреннее пространство коробки.")


def valid(obj, kind):
    prefix = "unit" if kind == "unit" else "auto"
    if not obj.pk or getattr(obj, f"{prefix}_test_only") or not getattr(obj, f"{prefix}_measured_at"):
        return False
    try:
        validate(obj, kind)
    except ValidationError:
        return False
    return getattr(obj, f"{prefix}_measurement_signature") == signature(obj, kind)


def confirm(obj, kind):
    prefix = "unit" if kind == "unit" else "auto"
    if getattr(obj, f"{prefix}_test_only"):
        raise ValidationError("Учебные параметры нельзя подтвердить как реальные замеры.")
    if not obj.pk:
        raise ValidationError("Сначала сохраните запись, затем подтвердите параметры.")
    validate(obj, kind)
    setattr(obj, f"{prefix}_measurement_signature", signature(obj, kind))
    setattr(obj, f"{prefix}_measured_at", timezone.now())
    fields = UNIT_FIELDS if kind == "unit" else BOX_FIELDS
    obj.save(
        update_fields=[*fields, f"{prefix}_measurement_signature", f"{prefix}_measured_at", "updated_at"]
    )


def clear_test_confirmation(obj, prefix, kwargs):
    if getattr(obj, f"{prefix}_test_only"):
        setattr(obj, f"{prefix}_measurement_signature", "")
        setattr(obj, f"{prefix}_measured_at", None)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                f"{prefix}_measurement_signature",
                f"{prefix}_measured_at",
            }
