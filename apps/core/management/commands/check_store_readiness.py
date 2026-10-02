"""Read-only preflight. No API calls, credentials, personal data or writes in its output."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import Product
from apps.content.models import SiteSettings
from apps.orders.models import DeliveryMethod, StoreSettings


def readiness_issues():
    issues = []
    site = SiteSettings.objects.first()
    for field, label in (
        ("legal_name", "подтверждённое наименование продавца"),
        ("inn", "ИНН продавца"),
        ("registration_number", "регистрационный номер продавца"),
        ("address", "адрес продавца"),
        ("return_address", "адрес возврата"),
        ("phone", "телефон покупательской поддержки"),
        ("email", "email покупательской поддержки"),
    ):
        if not site or not getattr(site, field, "").strip():
            issues.append(f"Не заполнено: {label}.")
    store = StoreSettings.objects.filter(pk=1).first()
    for field, label in (
        ("terms_text", "условия покупки"),
        ("privacy_text", "политика обработки данных"),
        ("delivery_text", "условия доставки и оплаты"),
        ("returns_text", "порядок возврата"),
    ):
        if not store or not getattr(store, field, "").strip():
            issues.append(f"Не опубликованы: {label}.")
    if not settings.CHECKOUT_ENABLED or not store or not store.checkout_enabled:
        issues.append("Оформление заказов выключено (нужны оба переключателя).")
    products = Product.objects.filter(status="published", purchasable=True)
    if not products.exists():
        issues.append("Нет опубликованных товаров для продажи.")
    if Product.objects.filter(status="published", sku__startswith="DEMO-").exists():
        issues.append(
            "Опубликованы демо-товары: оставьте их для обучения, снимите перед реальными продажами."
        )
    packages = ("package_weight_g", "package_length_cm", "package_width_cm", "package_height_cm")
    incomplete = sum(1 for row in products.values_list(*packages) if any(not value for value in row))
    if incomplete:
        issues.append(f"У {incomplete} товаров не заполнены вес/размеры транспортной упаковки.")
    methods = DeliveryMethod.objects.filter(active=True, type="cdek_pvz")
    if not methods.exists():
        issues.append("Нет активного способа доставки СДЭК до ПВЗ.")
    elif (
        methods.filter(cdek_tariff_code__isnull=True).exists() or methods.filter(cdek_tariff_code=0).exists()
    ):
        issues.append("Для СДЭК не указан тариф, соответствующий способу передачи посылок.")
    for name in ("ALFABANK_ENABLED", "CDEK_ENABLED"):
        if not getattr(settings, name):
            issues.append(f"{name} выключен.")
    for name in ("ALFABANK_USERNAME", "ALFABANK_PASSWORD", "CDEK_CLIENT_ID", "CDEK_CLIENT_SECRET"):
        if not getattr(settings, name):
            issues.append(f"Не задана переменная {name} (значения в отчёт не выводятся).")
    if not settings.CDEK_FROM_CITY_CODE:
        issues.append("Не задан CDEK_FROM_CITY_CODE: код Тольятти из справочника СДЭК.")
    from apps.orders.map_config import map_config

    if not map_config():
        issues.append("Некорректный CDEK_MAP_TILE_URL: карта недоступна, выбор ПВЗ остаётся в списке.")
    if settings.ALFABANK_TEST_MODE or settings.CDEK_TEST_MODE:
        issues.append("Включён тестовый режим интеграций; настоящие продажи ещё не проверены.")
    if not settings.ALFABANK_LIVE_APPROVED:
        issues.append("Запуск реальной оплаты не подтверждён (ALFABANK_LIVE_APPROVED=false).")
    if settings.ALFABANK_RECEIPT_MODE not in {"bank", "external"}:
        issues.append("Не согласована схема кассовых чеков (ALFABANK_RECEIPT_MODE).")
    elif settings.ALFABANK_RECEIPT_MODE == "bank":
        if settings.ALFABANK_TAX_SYSTEM not in range(6):
            issues.append("Не задана система налогообложения для чеков Альфа-Банка.")
        if products.filter(vat_code__isnull=True).exists():
            issues.append("Не заполнены ставки НДС товаров для чеков.")
        if methods.filter(vat_code__isnull=True).exists():
            issues.append("Не заполнена ставка НДС платной доставки для чека.")
    return issues


class Command(BaseCommand):
    help = "Проверить заполнение магазина перед запуском; без запросов к банку/СДЭК и без изменений."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true", help="Ненулевой код выхода при пробелах.")

    def handle(self, *args, **options):
        issues = readiness_issues()
        self.stdout.write("Проверка заполнения магазина (не одобрение банка и не юридическая экспертиза):")
        for issue in issues:
            self.stdout.write("- " + issue)
        if not issues:
            self.stdout.write("Проверяемые поля заполнены.")
        self.stdout.write(
            "Вручную: подтвердить продавца и тексты, сроки отправки, упаковку, чеки, тестовый платёж/возврат, "
            "реальный расчёт СДЭК и выпуск накладной после оплаты."
        )
        if options["strict"] and issues:
            raise CommandError(f"Незавершённых пунктов: {len(issues)}.")
