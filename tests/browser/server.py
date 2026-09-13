"""Disposable browser-test database. Never seeds the development/production catalog."""

import os
import sys
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
settings.CONTENT_VIDEO_PROVIDERS = ("youtube",)
settings.MAIN_ORIGIN = "http://localhost:8001"
settings.SHOP_ORIGIN = "http://shop.localhost:8001"
settings.CSRF_TRUSTED_ORIGINS = [settings.MAIN_ORIGIN, settings.SHOP_ORIGIN]
settings.CHECKOUT_ENABLED = True
settings.YOOKASSA_ENABLED = False
settings.TEMPLATES[0]["APP_DIRS"] = False
settings.TEMPLATES[0]["OPTIONS"]["loaders"] = [
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]
django.setup()

from django.core.management import call_command
from apps.catalog.models import Category, Product, ProductImage, ProductAttribute
from apps.orders.models import DeliveryMethod, StoreSettings
from django.core.files.base import ContentFile
from apps.content.models import Document, Video
from apps.reviews.models import Review
from datetime import date

call_command("migrate", verbosity=0)
call_command("flush", interactive=False, verbosity=0)
call_command("import_legacy_content", verbosity=0)
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
call_command("runserver", "127.0.0.1:8001", use_reloader=False)
