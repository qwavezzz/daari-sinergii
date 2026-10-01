"""Disposable browser-test database. Never seeds the development/production catalog."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_dev")
import django
from django.conf import settings

settings.DATABASES["default"] = {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": ROOT / "var" / "browser-tests.sqlite3",
}
(ROOT / "var").mkdir(exist_ok=True)
settings.PRIVATE_MEDIA_ROOT = ROOT / "var" / "browser-private-media"
settings.MEDIA_ROOT = ROOT / "var" / "browser-media"
settings.CONTENT_VIDEO_PROVIDERS = ("youtube",)
settings.MAIN_ORIGIN = "http://localhost:8001"
settings.SHOP_ORIGIN = "http://shop.localhost:8001"
settings.CSRF_TRUSTED_ORIGINS = [settings.MAIN_ORIGIN, settings.SHOP_ORIGIN]
settings.CHECKOUT_ENABLED = True
settings.ALFABANK_ENABLED = False
# Explicit test-only CDEK adapter. This file always uses a disposable SQLite database.
settings.CDEK_ENABLED = True
settings.CDEK_TEST_MODE = True
settings.CDEK_CLIENT_ID = "browser-fixture"
settings.CDEK_CLIENT_SECRET = "browser-fixture-not-a-credential"
settings.CDEK_FROM_CITY_CODE = 99999
settings.CDEK_YANDEX_API_KEY = "browser-fixture"
settings.TEMPLATES[0]["APP_DIRS"] = False
settings.TEMPLATES[0]["OPTIONS"]["loaders"] = [
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]
django.setup()

from django.core.management import call_command
from catalog.models import Category, Product, ProductImage, ProductAttribute
from orders.models import DeliveryMethod, StoreSettings
from django.core.files.base import ContentFile
from content.models import Document, Video
from reviews.models import Review
from datetime import date

call_command("migrate", verbosity=0)
call_command("flush", interactive=False, verbosity=0)
call_command("import_legacy_content", verbosity=0)
call_command("apply_seo_content", apply=True, verbosity=0)
category = Category.objects.create(name="Тестовые масла", slug="test-oils")
Category.objects.create(name="Тестовая пустая категория", slug="test-empty")
for index in range(20):
    product = Product.objects.create(
        name=f"Тестовый товар {index + 1}"
        + (" с длинным названием для проверки переноса и увеличения текста" if index == 0 else ""),
        slug=f"test-product-{index + 1}",
        sku=f"TEST-{index + 1:03}",
        price="1290.50",
        stock=50,
        status="published",
        purchasable=True,
        short_description="Только тестовые данные для проверки интерфейса. Не предложение о продаже.",
        description="Описание тестовой позиции. Проверяем чтение подробностей без JavaScript.",
        sort_order=index,
        package_weight_g=400,
        package_length_cm=20,
        package_width_cm=10,
        package_height_cm=10,
    )
    product.categories.add(category)
    ProductAttribute.objects.create(product=product, name="Назначение", value="Проверка интерфейса")
    if index == 1:
        product.short_description = "Тестовое длинное описание для проверки доступности. " * 15
        product.save(update_fields=["short_description"])
        review = Review.objects.create(
            author="Тестовый автор",
            organization="Автотест",
            date=date(2026, 9, 11),
            text="Это тестовый отзыв для проверки раскрытия длинного текста. " * 14,
            status="published",
            publication_basis="Искусственные данные, только для автотестов.",
        )
        review.products.add(product)
        video = Video.objects.create(
            title="Тестовое видео", provider="youtube", provider_id="test_video", status="published"
        )
        video.products.add(product)
        Document.objects.filter(is_declaration=False).first().products.add(product)
    if index < 2:
        for image_index in range(1 if index == 0 else 8):
            ProductImage.objects.create(
                product=product,
                alt="Тестовое изображение: логотип компании",
                image=ContentFile(
                    (ROOT / "public" / "assets" / "brand-mark-navy.png").read_bytes(),
                    name=f"test-{index}-{image_index}.png",
                ),
            )
Product.objects.create(
    name="Тестовый недоступный товар",
    slug="test-unavailable",
    sku="TEST-OFF",
    status="published",
    price="2000",
    stock=0,
)
StoreSettings.objects.create(
    checkout_enabled=True,
    terms_text="Тестовые условия, только для автотестов.",
    privacy_text="Тестовый документ, только для автотестов.",
    delivery_text="Тестовые условия получения, только для автотестов.",
)
DeliveryMethod.objects.create(
    name="Тестовый самовывоз", slug="test-pickup", price="0", address_required=False, active=True
)
DeliveryMethod.objects.create(
    name="Тестовая доставка", slug="test-delivery", price="350", address_required=True, active=True
)
DeliveryMethod.objects.create(
    name="Тестовый СДЭК до ПВЗ",
    slug="test-cdek",
    type="cdek_pvz",
    price="0",
    address_required=False,
    active=True,
    cdek_tariff_code=136,
)

from orders import cdek, shipping
from orders.cdek import DeliveryUnavailable


class BrowserCdekClient:
    """Deterministic network-free fixture; never imported by application runtime."""

    def pickup(self, code):
        if code not in {"TEST1", "TEST2"}:
            raise DeliveryUnavailable("Тестовый пункт не найден. Выберите другой пункт выдачи.")
        return {
            "code": code,
            "city_code": 44,
            "city": "Тестовый город",
            "address": "Тестовый адрес, 10",
            "name": "Тестовый пункт выдачи",
        }

    def calculate(self, tariff, pickup, packages):
        return {"price": "315.00", "period_min": 2, "period_max": 4}

    def offices(self, filters=None, *, response_headers=None):
        if response_headers is not None:
            response_headers["X-Total-Elements"] = "1"
        return [
            {
                "code": "TEST1",
                "name": "Тестовый пункт выдачи",
                "type": "PVZ",
                "location": {
                    "city_code": 44,
                    "city": "Тестовый город",
                    "address": "Тестовый адрес, 10",
                    "latitude": 53.5,
                    "longitude": 49.4,
                },
            }
        ]


shipping.CdekClient = BrowserCdekClient
cdek.CdekClient = BrowserCdekClient
call_command("runserver", "0.0.0.0:8001", use_reloader=False)
