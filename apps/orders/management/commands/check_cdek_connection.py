"""Explicit read-only provider smoke check: no orders, waybills or personal data."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError

from apps.orders.cdek import CdekClient


class Command(BaseCommand):
    help = "Проверить API СДЭК по ПВЗ: справочник и расчёт учебной посылки без создания отправления."

    def add_arguments(self, parser):
        parser.add_argument("--pvz", default="MOS4", help="Код ПВЗ назначения (по умолчанию MOS4).")
        parser.add_argument("--tariff", type=int, default=136)

    def handle(self, *args, **options):
        try:
            client = CdekClient()
            point = client.pickup(options["pvz"])
            quote = client.calculate(
                options["tariff"], point, [{"weight": 400, "length": 20, "width": 10, "height": 10}]
            )
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from None
        self.stdout.write("Среда СДЭК: " + ("тестовая" if settings.CDEK_TEST_MODE else "рабочая"))
        self.stdout.write(f"Отправление из города {settings.CDEK_FROM_CITY_CODE}; тариф {options['tariff']}.")
        self.stdout.write(f"ПВЗ {point['code']}: {point['city']}, {point['address']}")
        self.stdout.write(
            f"Полная стоимость по API: {quote['price']} ₽; срок {quote['period_min']}–{quote['period_max']} дн."
        )
        self.stdout.write("Учебная посылка 400 г, 20 × 10 × 10 см. Отправление не создавалось.")
