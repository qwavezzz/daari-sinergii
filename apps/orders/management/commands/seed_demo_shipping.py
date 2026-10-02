"""User-supplied fictional dimensions for local sandbox checkout, never measured data."""

from collections import Counter
from itertools import chain, combinations_with_replacement
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Category, Product
from apps.orders.models import PackingBox, PackingRecipe, PackingRecipeItem


PROFILES = {
    "demo-hydrolats": (150, 60, 60, 180),
    "demo-oils": (70, 40, 40, 100),
}
GIFT_SKU = "DEMO-HYDROLAT-SET"
GIFT_PROFILE = (500, 240, 60, 180)
RECIPE_PREFIX = "Учебная 02.10: "
BOXES = (
    ("demo-input-small", "Учебная малая коробка", (100, 100, 190), (110, 110, 200), 40, 10, 2000),
    ("demo-input-medium", "Учебная средняя коробка", (280, 180, 190), (290, 190, 200), 90, 20, 5000),
    ("demo-input-large", "Учебная большая коробка", (380, 280, 190), (390, 290, 200), 150, 40, 10000),
)
AXES = ("length", "width", "height")


def _require_local_sandbox():
    config = settings.DATABASES["default"]
    database = str(config["NAME"])
    in_memory = database == ":memory:" or database.startswith("file:memorydb_")
    if (
        not settings.DEBUG
        or not settings.CDEK_TEST_MODE
        or not settings.PAYMENT_STUB_ENABLED
        or settings.ALFABANK_ENABLED
        or config["ENGINE"] != "django.db.backends.sqlite3"
        or not (in_memory or Path(database).resolve().is_relative_to(Path(settings.BASE_DIR).resolve()))
    ):
        raise CommandError(
            "Учебные упаковки разрешены только в локальной SQLite: DEBUG, тестовый СДЭК, "
            "пробная оплата и выключенный Альфа-Банк."
        )


def _set_profile(product, profile):
    if product.package_measurement_signature or (
        PackingRecipeItem.objects.filter(product=product, recipe__test_only=False)
        .exclude(recipe__measurement_signature="")
        .exists()
    ):
        # A combined unit has no individual-package stamp: its measurements
        # are attested by the real recipes containing it. Protect even stale
        # or inactive stamps rather than replacing measured inputs with fiction.
        raise CommandError(f"У {product.sku} уже подтверждены реальные замеры; учебные данные не записаны.")
    weight, length, width, height = profile
    product.shipping_mode = "combined"
    product.unit_weight_g = weight
    product.unit_length_mm, product.unit_width_mm, product.unit_height_mm = length, width, height
    product.package_weight_g = weight
    product.package_length_cm, product.package_width_cm, product.package_height_cm = (
        (value + 9) // 10 for value in (length, width, height)
    )
    product.package_measured_at = None
    product.save(
        update_fields=[
            "shipping_mode",
            "unit_weight_g",
            "unit_length_mm",
            "unit_width_mm",
            "unit_height_mm",
            "package_weight_g",
            "package_length_cm",
            "package_width_cm",
            "package_height_cm",
            "package_measured_at",
            "updated_at",
        ]
    )


class Command(BaseCommand):
    help = "Учебные размеры гидролатов/масел и отдельный набор гидролатов; системы озонации не меняются."

    @transaction.atomic
    def handle(self, *args, **options):
        _require_local_sandbox()
        products = list(
            Product.objects.filter(sku__startswith="DEMO-", categories__slug__in=PROFILES)
            .exclude(categories__slug="demo-water")
            .distinct()
            .prefetch_related("categories")
            .order_by("sku")
        )
        if not products:
            raise CommandError(
                "В локальном каталоге нет демо-масел или гидролатов. Сначала добавьте демокаталог."
            )
        for product in products:
            families = {category.slug for category in product.categories.all()}.intersection(PROFILES)
            if len(families) != 1:
                raise CommandError(f"Для {product.sku} неоднозначна категория упаковки.")
            _set_profile(product, PROFILES[families.pop()])

        gift, created = Product.objects.get_or_create(
            sku=GIFT_SKU,
            defaults={
                "name": "Учебный подарочный набор гидролатов",
                "slug": "demo-hydrolat-gift-set",
                "price": "1000.00",
                "stock": 20,
                "status": "published",
                "purchasable": True,
                "short_description": "Учебный набор для проверки корзины, упаковки и доставки.",
                "description": "Вымышленный товар. Цена, остаток, состав и упаковка заданы только для тестирования. Не предложение о продаже.",
                "sort_order": 17,
            },
        )
        category, _ = Category.objects.get_or_create(slug="demo-sets", defaults={"name": "Наборы"})
        if created:
            gift.categories.add(category)
        _set_profile(gift, GIFT_PROFILE)
        products.append(gift)
        products.sort(key=lambda product: product.sku)

        boxes = []
        for code, name, inner, outer, tare, filler, limit in BOXES:
            if PackingBox.objects.filter(code=code, recipes__test_only=False).exists():
                raise CommandError(f"Коробка {code} связана с реальной схемой. Учебные данные не записаны.")
            box, _ = PackingBox.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "tare_weight_g": tare,
                    "max_weight_g": limit,
                    "active": True,
                    **{f"inner_{axis}_mm": value for axis, value in zip(AXES, inner)},
                    **{f"outer_{axis}_mm": value for axis, value in zip(AXES, outer)},
                },
            )
            boxes.append((box, filler))

        # These authored trial arrangements place protected units upright in one
        # row. They are fictional test inputs, not a production fitting algorithm.
        compositions = (
            combo
            for count in range(1, 4)
            for combo in combinations_with_replacement(range(len(products)), count)
        )
        extra = ((index,) * count for index in range(len(products)) for count in (4, 6))
        names = []
        for combination in chain(compositions, extra):
            units = [products[index] for index in combination]
            row_size = (
                sum(product.unit_length_mm for product in units),
                max(product.unit_width_mm for product in units),
                max(product.unit_height_mm for product in units),
            )
            selected = next(
                (
                    (box, filler)
                    for box, filler in boxes
                    if all(size <= getattr(box, f"inner_{axis}_mm") for axis, size in zip(AXES, row_size))
                ),
                None,
            )
            if selected is None:
                continue
            box, filler = selected
            counts = Counter(product.pk for product in units)
            label = " + ".join(
                f"{product.sku} × {counts[product.pk]}" for product in products if product.pk in counts
            )
            name = RECIPE_PREFIX + label
            if PackingRecipe.objects.filter(name=name, test_only=False).exists():
                raise CommandError(f"Схема {name} уже используется как реальная. Учебные данные не записаны.")
            recipe, _ = PackingRecipe.objects.update_or_create(
                name=name,
                defaults={
                    "box": box,
                    "packing_weight_g": filler,
                    "measured_weight_g": sum(product.unit_weight_g for product in units)
                    + box.tare_weight_g
                    + filler,
                    **{f"outer_{axis}_mm": getattr(box, f"outer_{axis}_mm") for axis in AXES},
                    "instructions": (
                        "УЧЕБНАЯ СХЕМА. Реальная сборка и замеры не проводились. "
                        "Условная укладка: поставить упакованные единицы вертикально в один ряд вдоль длины коробки. "
                        "Вес тары и общего наполнителя добавляется к заданному весу товаров."
                    ),
                    "active": True,
                    "test_only": True,
                    "measurement_signature": "",
                    "measured_at": None,
                },
            )
            for product_id, count in counts.items():
                PackingRecipeItem.objects.update_or_create(
                    recipe=recipe,
                    product_id=product_id,
                    defaults={"quantity": count},
                )
            recipe.items.exclude(product_id__in=counts).delete()
            recipe.validate_measurements()
            names.append(name)
        PackingRecipe.objects.filter(name__startswith=RECIPE_PREFIX, test_only=True).exclude(
            name__in=names
        ).update(active=False)
        self.stdout.write(
            f"Учебные параметры: {len(products)} товаров, {len(boxes)} коробки, {len(names)} схем. "
            "Системы озонации и прежние наборы масел не менялись. Реальные замеры не подтверждались."
        )
        self.stdout.write(
            "Новый набор гидролатов: условные 1000 руб., 24 x 6 x 18 см, 500 г без общей транспортной коробки."
        )
