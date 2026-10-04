"""Read-only preflight. No API calls, credentials, personal data or writes in its output."""

import json
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.catalog.models import Product
from apps.content.models import SiteSettings
from apps.core.acceptance import configuration_digest
from apps.core.models import StoreAcceptance
from apps.orders.models import DeliveryMethod, PackingRecipe, StoreSettings
from apps.orders.notifications import validate_configuration


def packing_coverage(products):
    """Confirmed singleton recipes provide safe fallbacks for mixed baskets."""
    covered = set()
    recipes = (
        PackingRecipe.objects.filter(active=True, test_only=False, box__active=True)
        .select_related("box")
        .prefetch_related("items__product")
    )
    for recipe in recipes:
        rows = list(recipe.items.all())
        if (
            len(rows) == 1
            and rows[0].quantity == 1
            and recipe.measurements_valid_for_snapshot(box=recipe.box, rows=rows)
        ):
            covered.add(rows[0].product_id)
    return [
        product
        for product in products
        if not (
            product.package_measurements_valid
            if product.shipping_mode == "individual"
            else product.pk in covered
        )
    ]


def readiness_issues(stage="live"):
    issues = []
    site = SiteSettings.objects.first()
    for field, label in (
        ("legal_name", "подтверждённое наименование продавца"),
        ("inn", "ИНН продавца"),
        ("registration_number", "регистрационный номер продавца"),
        ("address", "адрес продавца"),
        ("postal_address", "почтовый адрес для обращений"),
        ("return_address", "адрес возврата"),
        ("phone", "телефон покупательской поддержки"),
        ("email", "email покупательской поддержки"),
    ):
        if not site or not getattr(site, field, "").strip():
            issues.append(f"Не заполнено: {label}.")
    if site:
        if site.seller_type == "company" and not site.kpp:
            issues.append("Не заполнен КПП организации.")
        try:
            site.full_clean()
        except ValidationError:
            issues.append("Реквизиты продавца не проходят проверку формата в админке.")
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
    products = list(
        Product.objects.filter(status="published", purchasable=True).prefetch_related("images", "attributes")
    )
    if not products:
        issues.append("Нет опубликованных товаров для продажи.")
    if Product.objects.filter(status="published", sku__startswith="DEMO-").exists():
        issues.append("Опубликованы демо-товары: снимите их перед подачей в банк и продажами.")
    for product in products:
        if not product.description.strip() or not product.images.exists() or not product.attributes.exists():
            issues.append(f"Товар #{product.pk}: нужны описание, фотография и характеристики.")
        if any(
            not picture.image or not picture.image.storage.exists(picture.image.name)
            for picture in product.images.all()
        ):
            issues.append(f"Товар #{product.pk}: файл опубликованной фотографии отсутствует.")
        if product.price is None or product.price <= 0:
            issues.append(f"Товар #{product.pk}: нет действительной цены.")
    if products and not any(product.available_quantity > 0 for product in products):
        issues.append("Нет доступного остатка ни у одного продаваемого товара.")
    uncovered = packing_coverage(products)
    if uncovered:
        issues.append(
            f"У {len(uncovered)} товаров не подтверждены вес/размеры транспортной упаковки: "
            "нужны замеры отдельной посылки либо действующая неучебная схема одной единицы. "
            "Товары: " + ", ".join(f"#{p.pk}" for p in uncovered) + "."
        )
    methods = DeliveryMethod.objects.filter(active=True)
    cdek = methods.filter(type="cdek_pvz")
    if not cdek.exists():
        issues.append("Нет активного способа доставки СДЭК до ПВЗ.")
    elif cdek.filter(cdek_tariff_code__isnull=True).exists() or cdek.filter(cdek_tariff_code=0).exists():
        issues.append("Для СДЭК не указан тариф, соответствующий способу передачи посылок.")
    if not settings.CDEK_ENABLED:
        issues.append("CDEK_ENABLED выключен.")
    for name in ("CDEK_CLIENT_ID", "CDEK_CLIENT_SECRET", "CDEK_FROM_CITY_CODE"):
        if not getattr(settings, name):
            issues.append(f"Не задана переменная {name} (значение скрыто).")
    if settings.CDEK_TEST_MODE or settings.CDEK_DEMO_QUOTES_ENABLED:
        issues.append("Расчёт СДЭК использует тестовый/учебный режим; нужен рабочий договор.")
    if settings.PAYMENT_STUB_ENABLED:
        issues.append("Пробная оплата включена (PAYMENT_STUB_ENABLED): она не проверяет банк и письма.")
    try:
        validate_configuration()
    except ImproperlyConfigured as exc:
        issues.append("Почта: " + str(exc))
    if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
        issues.append("Для приёмки нужен SMTP, а не локальный просмотр писем.")
    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        issues.append("Не заданы учётные данные SMTP.")
    if settings.DEBUG or settings.DEVELOPMENT:
        issues.append("Проверка выполняется в окружении разработки; запуск требует production-настроек.")
    if not settings.SHOP_ORIGIN.startswith("https://"):
        issues.append("SHOP_ORIGIN должен использовать HTTPS.")
    if not settings.DATABASES["default"]["ENGINE"].endswith("postgresql"):
        issues.append("Для рабочего магазина нужен PostgreSQL и проверка конкурентных заказов.")
    for name in ("SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT"):
        if not getattr(settings, name):
            issues.append(f"Не включена защита {name}.")
    if not 60 <= settings.ORDER_EMAIL_LINK_MAX_AGE <= 90 * 86400:
        issues.append("Срок email-ссылок должен быть от 60 секунд до 90 дней.")
    if stage == "review" and settings.ALFABANK_ENABLED and settings.ALFABANK_TEST_MODE:
        issues.append("На публичном магазине отключите тестовый банк; приёмку проводите на отдельном стенде.")
    if stage == "live":
        for name in ("ALFABANK_ENABLED", "ALFABANK_USERNAME", "ALFABANK_PASSWORD", "ALFABANK_LIVE_APPROVED"):
            if not getattr(settings, name):
                issues.append(f"Не настроен {name} (значение скрыто).")
        if settings.ALFABANK_TEST_MODE:
            issues.append("Альфа-Банк в тестовом режиме: настоящие оплаты выключены.")
        if settings.ALFABANK_RECEIPT_MODE not in {"bank", "external"}:
            issues.append("Не согласована схема кассовых чеков (ALFABANK_RECEIPT_MODE).")
        if settings.ALFABANK_RECEIPT_MODE == "bank":
            if settings.ALFABANK_TAX_SYSTEM not in range(6):
                issues.append("Не задана система налогообложения для чеков Альфа-Банка.")
            if any(product.vat_code not in range(1, 13) for product in products):
                issues.append("Не заполнены допустимые ставки НДС товаров для чеков.")
            if any(
                method.vat_code not in range(1, 13)
                for method in methods
                if method.price or method.type == "cdek_pvz"
            ):
                issues.append("Не заполнена ставка НДС платной доставки для чека.")
    required = {"catalog", "shipping", "email", "checkout", "operations"}
    if stage == "live":
        required |= {"payment", "fiscal"}
    records = {row.kind: row for row in StoreAcceptance.objects.filter(kind__in=required)}
    for key, label in StoreAcceptance.Check.choices:
        if key not in required:
            continue
        record = records.get(key)
        if not record or not record.reference.strip():
            issues.append(f"Нет протокола приёмки: {label}.")
        elif record.confirmed_at < timezone.now() - timedelta(
            days=90
        ) or record.configuration_digest != configuration_digest(key):
            issues.append(
                f"Приёмку нужно повторить после изменения настроек/данных или истечения 90 дней: {label}."
            )
    return issues


class Command(BaseCommand):
    help = "Готовность к подаче в банк (review) или реальным продажам (live); без сети и изменений."

    def add_arguments(self, parser):
        parser.add_argument("--stage", choices=["review", "live"], default="live")
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        issues = readiness_issues(options["stage"])
        if options["json"]:
            self.stdout.write(
                json.dumps(
                    {"stage": options["stage"], "ready": not issues, "issues": issues}, ensure_ascii=False
                )
            )
        else:
            self.stdout.write(f"Готовность магазина: {options['stage']}. Проверка не заменяет решение банка.")
            for issue in issues:
                self.stdout.write("- " + issue)
            if not issues:
                self.stdout.write("Автоматические проверки пройдены; актуальные протоколы приёмки записаны.")
        if options["strict"] and issues:
            raise CommandError(f"Незавершённых пунктов: {len(issues)}.")
