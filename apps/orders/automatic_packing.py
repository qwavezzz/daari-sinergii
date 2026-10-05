"""Automatic packing of verified, protected product envelopes into available boxes."""

from collections import Counter
from copy import deepcopy
from decimal import Decimal
from math import prod

from django.core.exceptions import ValidationError
from django.db.models import Q

from .auto_geometry import Budget, SearchLimit, fit_all, fit_some
from .auto_profiles import BOX_FIELDS, UNIT_FIELDS, validate
from .cdek import DeliveryUnavailable
from .models import PackingBox


MAX_AUTO_BOXES = 64
AXES = ("length", "width", "height")


def available_boxes(allow_test):
    query = PackingBox.objects.filter(active=True, auto_enabled=True)
    if allow_test:
        query = query.filter(
            Q(auto_test_only=True) | (~Q(auto_measurement_signature="") & Q(auto_measured_at__isnull=False))
        )
    else:
        query = query.filter(auto_test_only=False, auto_measured_at__isnull=False).exclude(
            auto_measurement_signature=""
        )
    boxes = list(query.order_by("pk")[: MAX_AUTO_BOXES + 1])
    if len(boxes) > MAX_AUTO_BOXES:
        raise DeliveryUnavailable("Слишком много коробок для автоподбора. Отключите недоступные типоразмеры.")
    return boxes


def configuration(items, boxes):
    def fields(obj, names):
        return {
            name: (
                str(value)
                if isinstance(value, Decimal)
                else value.isoformat()
                if hasattr(value, "isoformat")
                else value
            )
            for name in names
            for value in [getattr(obj, name)]
        }

    return {
        "version": 1,
        "products": [
            fields(item.product, ("id", *UNIT_FIELDS, "unit_measurement_signature", "unit_measured_at"))
            for item in items
        ],
        "boxes": [
            fields(box, ("id", "code", *BOX_FIELDS, "auto_measurement_signature", "auto_measured_at"))
            for box in boxes
        ],
    }


def cart_configuration(items, allow_test):
    return configuration(items, available_boxes(allow_test)) if items else None


def _score(parcels):
    return (
        len(parcels),
        sum(prod((p["dimensions_mm"][a] + 9) // 10 for a in AXES) for p in parcels),
        sum(p["weight_g"] for p in parcels),
        sum(Decimal(p["packing_price"]) for p in parcels),
        tuple(p["box_code"] for p in parcels),
    )


def _key(parcels):
    return (
        tuple(
            sorted((p["weight_g"], *sorted((p["dimensions_mm"][a] + 9) // 10 for a in AXES)) for p in parcels)
        ),
        sum(Decimal(p["packing_price"]) for p in parcels),
    )


class AutomaticPacking:
    def __init__(self, items, *, allow_test=False):
        self.items = items
        if not items or any(type(item.quantity) is not int or item.quantity < 1 for item in items):
            raise DeliveryUnavailable("Проверьте количество товаров для упаковки.")
        if sum(item.quantity for item in items) > 100:
            raise DeliveryUnavailable("Для более 100 единиц требуется подбор упаковки сотрудником.")
        boxes = available_boxes(allow_test)
        self.configuration = configuration(items, boxes)
        self.boxes = []
        for box in boxes:
            try:
                validate(box, "box")
            except ValidationError:
                continue
            if box.auto_measurements_valid or (allow_test and box.auto_test_only):
                self.boxes.append(box)
        if not self.boxes:
            raise DeliveryUnavailable(
                "Нет доступной коробки с подтверждёнными параметрами автоподбора. Свяжитесь с магазином."
            )
        self.boxes.sort(
            key=lambda b: (prod(getattr(b, f"outer_{a}_mm") for a in AXES), b.tare_weight_g, b.pk)
        )
        self.groups = {}
        for item in items:
            product = item.product
            try:
                validate(product, "unit")
            except ValidationError as exc:
                raise DeliveryUnavailable(
                    f"Для «{product.name}» не заполнены параметры автоматической упаковки."
                ) from exc
            if not (product.auto_measurements_valid or (allow_test and product.unit_test_only)):
                raise DeliveryUnavailable(f"Для «{product.name}» не подтверждены замеры товара с защитой.")
            if type(item.quantity) is not int or item.quantity < 1:
                raise DeliveryUnavailable("Проверьте количество товаров для упаковки.")
            for number in range(item.quantity):
                self.groups.setdefault(product.unit_packing_group, []).append(
                    {
                        "product_id": product.pk,
                        "sku": product.sku,
                        "name": product.name,
                        "number": number,
                        "dimensions": tuple(getattr(product, f"unit_{a}_mm") for a in AXES),
                        "weight": product.unit_weight_g,
                        "rotate": product.unit_allow_rotation,
                        "stack_limit": product.unit_stack_limit_g,
                        "confirmed": product.auto_measurements_valid,
                    }
                )
        if sum(len(group) for group in self.groups.values()) > 100:
            raise DeliveryUnavailable("Для более 100 единиц требуется подбор упаковки сотрудником.")

    @staticmethod
    def _space(box, limits):
        overhead = box.tare_weight_g + box.auto_filler_weight_g
        maximum = min(box.max_weight_g, limits[1]) if limits and limits[1] else box.max_weight_g
        inner = tuple(getattr(box, f"inner_{a}_mm") - 2 * box.auto_padding_mm for a in AXES)
        return inner, maximum - overhead

    @staticmethod
    def _parcel(box, placed):
        counts = Counter(row["unit"]["product_id"] for row in placed)
        products = {row["unit"]["product_id"]: row["unit"] for row in placed}
        placements = [
            {
                "product_id": row["unit"]["product_id"],
                "sku": row["unit"]["sku"],
                "position_mm": [n + box.auto_padding_mm for n in row["pos"]],
                "size_mm": list(row["size"]),
            }
            for row in placed
        ]
        return {
            "kind": "automatic",
            "recipe_id": None,
            "recipe_name": "Автоматическая укладка",
            "box_code": box.code,
            "box_name": box.name,
            "weight_g": sum(row["unit"]["weight"] for row in placed)
            + box.tare_weight_g
            + box.auto_filler_weight_g,
            "weight_basis": "calculated",
            "assembly_measured": False,
            "packing_price": str(box.auto_price if box.auto_price_mode == "charge" else Decimal("0.00")),
            "dimensions_mm": {a: getattr(box, f"outer_{a}_mm") for a in AXES},
            "contents": [
                {
                    "product_id": pk,
                    "sku": products[pk]["sku"],
                    "name": products[pk]["name"],
                    "quantity": counts[pk],
                }
                for pk in sorted(counts)
            ],
            "placements": placements,
            "instructions": "Автоподбор по подтверждённым параметрам. Использовать указанную коробку и индивидуальную защиту. "
            f"Общие материалы: {box.auto_filler_weight_g} г; отступ от стенок: {box.auto_padding_mm} мм. "
            "Координаты X/Y/Z от внутреннего угла у дна, размеры защищённых единиц, всё в мм:\n"
            + "\n".join(
                f"{p['sku']}: позиция {p['position_mm']}, габариты {p['size_mm']}" for p in placements
            )
            + "\nПеред отправкой проверить полный вес и внешние размеры закрытой посылки.",
            "measurements_confirmed": box.auto_measurements_valid
            and all(row["unit"]["confirmed"] for row in placed),
            "test_only": box.auto_test_only or any(not row["unit"]["confirmed"] for row in placed),
        }

    def _group_options(self, units, limits, limit, budget):
        singles = []
        for box in self.boxes:
            inner, capacity = self._space(box, limits)
            weight = sum(unit["weight"] for unit in units) + box.tare_weight_g + box.auto_filler_weight_g
            if limits and weight < limits[0]:
                continue
            placed = fit_all(units, inner, capacity, budget)
            if placed is not None:
                singles.append([self._parcel(box, placed)])
        if singles:
            return self._select(singles, limit)
        plans = []
        # Different first boxes produce useful alternative splits. Every parcel
        # is independently checked; a box count is not an estimate of coverage.
        for first in self.boxes:
            remaining, parcels = list(units), []
            while remaining:
                choices = []
                for box in [first] if not parcels else self.boxes:
                    inner, capacity = self._space(box, limits)
                    placed = fit_some(remaining, inner, capacity, budget)
                    if not placed:
                        continue
                    parcel = self._parcel(box, placed)
                    if limits and parcel["weight_g"] < limits[0]:
                        continue
                    choices.append((placed, parcel))
                if not choices:
                    break
                placed, parcel = min(choices, key=lambda c: (-len(c[0]), _score([c[1]])))
                consumed = {(r["unit"]["product_id"], r["unit"]["number"]) for r in placed}
                remaining = [u for u in remaining if (u["product_id"], u["number"]) not in consumed]
                parcels.append(parcel)
            if not remaining:
                plans.append(parcels)
        if not plans:
            raise DeliveryUnavailable(
                "Товары не помещаются в доступные коробки с учётом защиты и ограничений веса. Нужен подбор сотрудником."
            )
        return self._select(plans, limit)

    @staticmethod
    def _select(plans, limit):
        minimum = min(len(p) for p in plans)
        selected = {}
        for plan in sorted(plans, key=_score):
            if len(plan) == minimum:
                selected.setdefault(_key(plan), plan)
        return list(selected.values())[:limit]

    def options(self, *, limits=None, limit=8):
        budget = Budget()
        plans = [[]]
        try:
            for _, units in sorted(self.groups.items()):
                choices = self._group_options(units, limits, limit, budget)
                plans = self._select([deepcopy(p) + c for p in plans for c in choices], limit)
        except SearchLimit as exc:
            raise DeliveryUnavailable(
                "Автоподбор этой корзины требует проверки сотрудником: превышен предел поиска укладки."
            ) from exc
        return plans
