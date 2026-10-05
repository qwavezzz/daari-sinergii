"""Idempotent reference drafts and isolated examples; never fabricate live measurements."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Product
from apps.orders.models import PackingBox


# Reference catalogue only, checked 2026-10-05. No inference of usable inner
# space, gross outer dimensions, tare, stock availability or local retail price.
CDEK_DRAFTS = (
    ("xs", "XS", "171 × 121 × 89"),
    ("s", "S", "216 × 200 × 110"),
    ("m", "M", "330 × 250 × 155"),
    ("l", "L", "310 × 250 × 380"),
    ("xl", "XL", "600 × 350 × 300"),
)


class Command(BaseCommand):
    help = (
        "Добавить черновики коробок СДЭК; --with-demo также создаёт отдельные учебные профили без публикации."
    )

    def add_arguments(self, parser):
        parser.add_argument("--with-demo", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        for code, label, dimensions in CDEK_DRAFTS:
            _, added = PackingBox.objects.get_or_create(
                code=f"cdek-posylochka-{code}",
                defaults={
                    "name": f"СДЭК — Посылочка {label}",
                    "supplier": "cdek",
                    "active": False,
                    "auto_enabled": False,
                    "source_url": "https://cdek.promo/shop",
                    "reference_note": f"Ориентир каталога cdek.promo на 05.10.2026: {dimensions} мм. "
                    "Проверить конкретную коробку в пункте отправления: наличие, внутренние и внешние размеры, вес тары, допустимую нагрузку. "
                    "Это черновик, не подтверждённые размеры и не подключение тарифа «Посылочка».",
                },
            )
            created += int(added)
        self.stdout.write(f"CDEK_DRAFTS_CREATED: {created}; existing records preserved")
        if not options["with_demo"]:
            return
        for code, inner, outer, tare in (
            ("small", (90, 90, 140), (100, 100, 150), 40),
            ("shared", (210, 160, 160), (220, 170, 170), 80),
            ("large", (310, 240, 210), (320, 250, 220), 130),
        ):
            existing = PackingBox.objects.filter(code=f"demo-auto-{code}").first()
            if existing and (not existing.auto_test_only or existing.auto_measurement_signature):
                raise CommandError(
                    "Reserved demo box code already belongs to a non-demo record; rolled back."
                )
            PackingBox.objects.get_or_create(
                code=f"demo-auto-{code}",
                defaults={
                    "name": f"УЧЕБНАЯ — автоподбор {code}",
                    "supplier": "demo",
                    "active": True,
                    "auto_enabled": True,
                    "auto_test_only": True,
                    "auto_filler_weight_g": 20,
                    "auto_padding_mm": 5,
                    "auto_price_mode": "included",
                    "max_weight_g": 5000,
                    "tare_weight_g": tare,
                    **{f"inner_{a}_mm": v for a, v in zip(("length", "width", "height"), inner)},
                    **{f"outer_{a}_mm": v for a, v in zip(("length", "width", "height"), outer)},
                    "reference_note": "Вымышленные параметры для предпросмотра. Не типоразмер и не цена СДЭК.",
                },
            )
        for suffix, weight, width, height in (("A", 150, 60, 120), ("B", 100, 50, 100)):
            sku = f"DEMO-AUTO-{suffix}"
            existing = Product.objects.filter(sku=sku).first()
            if existing and (
                not existing.unit_test_only
                or existing.unit_measurement_signature
                or existing.status != "draft"
                or existing.purchasable
            ):
                raise CommandError(
                    "Reserved demo product already belongs to a live/published record; rolled back."
                )
            Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": f"УЧЕБНЫЙ товар для автоподбора {suffix}",
                    "slug": f"demo-auto-{suffix.lower()}",
                    "price": "1290.00",
                    "stock": 0,
                    "status": "draft",
                    "purchasable": False,
                    "shipping_mode": "automatic",
                    "unit_test_only": True,
                    "unit_weight_g": weight,
                    "unit_length_mm": width,
                    "unit_width_mm": width,
                    "unit_height_mm": height,
                    "description": "Только для проверки автоматической укладки. Параметры вымышлены; покупка недоступна.",
                },
            )
        self.stdout.write(
            "DEMO_PROFILES_READY: DEMO-AUTO-A, DEMO-AUTO-B; no publication or measurement confirmations"
        )
