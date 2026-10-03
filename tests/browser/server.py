"""Disposable browser-test database. Never seeds the development/production catalog."""

import os
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
# These directories belong exclusively to this disposable test database. Keeping
# previous imports used to accumulate a fresh copy of every PDF on each run.
for fixture_dir in (settings.PRIVATE_MEDIA_ROOT, settings.MEDIA_ROOT):
    if fixture_dir.is_symlink() or fixture_dir.resolve() != ROOT / "var" / fixture_dir.name:
        raise RuntimeError("Unsafe browser fixture directory")
    if fixture_dir.exists():
        shutil.rmtree(fixture_dir)
    fixture_dir.mkdir(parents=True)
settings.CONTENT_VIDEO_PROVIDERS = ("youtube",)
settings.MAIN_ORIGIN = "http://localhost:8001"
settings.SHOP_ORIGIN = "http://shop.localhost:8001"
settings.CSRF_TRUSTED_ORIGINS = [settings.MAIN_ORIGIN, settings.SHOP_ORIGIN]
settings.CHECKOUT_ENABLED = True
settings.ALFABANK_ENABLED = False
settings.PAYMENT_STUB_ENABLED = True
# Explicit test-only CDEK adapter. This file always uses a disposable SQLite database.
settings.CDEK_ENABLED = True
settings.CDEK_TEST_MODE = True
settings.CDEK_CLIENT_ID = "browser-fixture"
settings.CDEK_CLIENT_SECRET = "browser-fixture-not-a-credential"
settings.CDEK_FROM_CITY_CODE = 99999
settings.TEMPLATES[0]["APP_DIRS"] = False
settings.TEMPLATES[0]["OPTIONS"]["loaders"] = [
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]
django.setup()

from django.core.management import call_command
from apps.catalog.models import Category, Product, ProductImage, ProductAttribute
from apps.orders.models import DeliveryMethod, StoreSettings
from apps.content.management.commands.setup_customer_pages import load_customer_copy
from django.core.files.base import ContentFile
from apps.content.models import Document, Video
from apps.reviews.models import Review
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
                    (ROOT / "assets" / "source" / "brand" / "brand-mark-navy.png").read_bytes(),
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
    **load_customer_copy()[0]["pages"],
)
DeliveryMethod.objects.create(
    name="Тестовый самовывоз", slug="test-pickup", price="0", address_required=False, active=True
)
DeliveryMethod.objects.create(
    name="Тестовая доставка", slug="test-delivery", price="350", address_required=True, active=True
)
# Credentials and orders below exist only in this disposable browser-test database.
import uuid
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from apps.orders.models import Order, OrderItem

call_command("setup_roles", verbosity=0)
owner = get_user_model().objects.create_user("browser-owner", password="browser-fixture-only", is_staff=True)
owner.groups.add(Group.objects.get(name="Владелец магазина"))
StoreSettings.objects.filter(pk=1).update(manager_email="manager@example.test")
sample = Order.objects.create(
    checkout_key=uuid.uuid4(),
    session_key="browser-admin-fixture",
    name="Тестовый покупатель",
    phone="+79000000000",
    email="buyer@example.test",
    delivery_method="Тестовый самовывоз",
    subtotal="1290.50",
    delivery_price="0",
    total="1290.50",
    financial_status="paid",
    test_mode=True,
    terms_accepted_at=timezone.now(),
)
OrderItem.objects.create(
    order=sample,
    product=Product.objects.get(sku="TEST-001"),
    name="Тестовый товар",
    sku="TEST-001",
    unit_price="1290.50",
    quantity=1,
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

from apps.orders import cdek, shipping
from apps.orders.cdek import DeliveryUnavailable
from apps.orders.models import PackingBox, PackingRecipe, PackingRecipeItem

# Synthetic measured arrangements exist only in the disposable test database.
packing_products = list(Product.objects.filter(sku__in=["TEST-019", "TEST-020"]).order_by("sku"))
for product in packing_products:
    product.shipping_mode = "combined"
    product.unit_weight_g = 300
    product.unit_length_mm = 50
    product.unit_width_mm = 50
    product.unit_height_mm = 100
    product.save()
packing_box = PackingBox.objects.create(
    name="Тестовая коробка для сборки",
    code="browser-packing-box",
    inner_length_mm=200,
    inner_width_mm=100,
    inner_height_mm=150,
    outer_length_mm=210,
    outer_width_mm=110,
    outer_height_mm=160,
    tare_weight_g=50,
    max_weight_g=5000,
)
for name, counts, weight, confirmed in (
    ("Тестовая пара товаров", (1, 1), 700, True),
    ("Черновик для проверки замеров", (2, 1), 1000, False),
):
    recipe = PackingRecipe.objects.create(
        name=name,
        box=packing_box,
        packing_weight_g=25,
        measured_weight_g=weight,
        outer_length_mm=211,
        outer_width_mm=111,
        outer_height_mm=161,
        instructions="Только тест: поставить вертикально и разделить вставками.",
        active=True,
    )
    for product, count in zip(packing_products, counts):
        PackingRecipeItem.objects.create(recipe=recipe, product=product, quantity=count)
    if confirmed:
        recipe.confirm_measurements()


class BrowserCdekClient:
    """Deterministic network-free fixture; never imported by application runtime."""

    token_key = "browser-fixture-cdek"

    def office_choices(self, city_code, page):
        return {
            "offices": [
                {
                    "code": "TEST1",
                    "name": "Тестовый пункт выдачи",
                    "address": "Тестовый адрес, 10",
                    "work_time": "Пн–Пт 9–18",
                    "latitude": 53.5078,
                    "longitude": 49.4204,
                },
                {
                    "code": "TEST2",
                    "name": "Второй тестовый пункт",
                    "address": "Другой тестовый адрес, 20",
                    "work_time": "Ежедневно 10–20",
                    "latitude": 53.5138,
                    "longitude": 49.4354,
                },
            ],
            "next_page": None,
        }

    def map_points(self, page):
        data = self.office_choices(44, 0)
        for point in data["offices"]:
            point.update(city_code=99999, city="Тестовый город", region="Тестовая область")
        return data

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

    def calculate(self, tariff, pickup, packages, *, declared_value=None):
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
call_command("runserver", "127.0.0.1:8001", use_reloader=False)
