"""Enable a local rehearsal without changing production or non-demo products."""

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Product
from apps.orders.models import DeliveryMethod, StoreSettings


class Command(BaseCommand):
    help = "Включить локальный пробный заказ: демо-упаковка, СДЭК до ПВЗ, заглушка оплаты."

    @transaction.atomic
    def handle(self, *args, **options):
        if (
            not settings.DEBUG
            or not settings.PAYMENT_STUB_ENABLED
            or settings.ALFABANK_ENABLED
            or not settings.CDEK_TEST_MODE
            or not settings.DATABASES["default"]["ENGINE"].endswith("sqlite3")
        ):
            raise CommandError(
                "Команда только для локального SQLite, DEBUG, тестового СДЭК и пробной оплаты "
                "при выключенном Альфа-Банке."
            )
        call_command("setup_customer_pages", refresh_defaults=True, stdout=self.stdout)
        store = StoreSettings.objects.get(pk=1)
        store.checkout_enabled = True
        store.save(update_fields=["checkout_enabled", "updated_at"])
        # Distinct slug avoids overwriting a delivery method already configured by the owner.
        method, _ = DeliveryMethod.objects.get_or_create(
            slug="cdek-local-rehearsal",
            defaults={
                "name": "СДЭК — пункт выдачи",
                "type": "cdek_pvz",
                "price": 0,
                "cdek_tariff_code": 136,
                "address_required": False,
            },
        )
        DeliveryMethod.objects.filter(is_default=True).exclude(pk=method.pk).update(is_default=False)
        method.active, method.is_default = True, True
        method.save(update_fields=["active", "is_default"])
        updated = 0
        fields = {
            "package_weight_g": 400,
            "package_length_cm": 20,
            "package_width_cm": 10,
            "package_height_cm": 10,
        }
        for product in Product.objects.filter(sku__startswith="DEMO-"):
            missing = [field for field in fields if not getattr(product, field)]
            if missing:
                for field in missing:
                    setattr(product, field, fields[field])
                product.save(update_fields=[*missing, "updated_at"])
                updated += 1
        self.stdout.write(
            f"Пробное оформление включено. Демо-упаковка добавлена для {updated} товаров: "
            "400 г, 20 × 10 × 10 см за штуку. Это учебные параметры, не измерения реальных товаров."
        )
        self.stdout.write(
            "Тариф 136 — сдача в ПВЗ и получение в ПВЗ. Город отправления задаёт CDEK_FROM_CITY_CODE. "
            "Реальных списаний и накладных нет."
        )
