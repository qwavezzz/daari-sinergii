from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.demo_data import CATEGORIES, DEMO_NOTICE, PRODUCTS
from catalog.models import Category, Product, ProductAttribute, ProductImage


class Command(BaseCommand):
    help = "Добавить 16 вымышленных товаров для локального просмотра. Существующие записи не меняются."

    def handle(self, *args, **options):
        if not settings.DEBUG or settings.CHECKOUT_ENABLED or settings.YOOKASSA_ENABLED:
            raise CommandError("Демокаталог доступен только локально, при выключенных оформлении и ЮKassa.")

        asset_dir = Path(__file__).resolve().parents[2] / "demo_assets"
        images = {key: (asset_dir / f"{key}.webp").read_bytes() for key in {p["image"] for p in PRODUCTS}}
        created_count = 0
        with transaction.atomic():
            categories = {
                slug: Category.objects.get_or_create(
                    slug=slug,
                    defaults={
                        "name": name,
                        "description": "Демонстрационная категория для предварительного просмотра магазина.",
                        "sort_order": index,
                    },
                )[0]
                for index, (slug, name) in enumerate(CATEGORIES)
            }
            for index, entry in enumerate(PRODUCTS, start=1):
                sku = f"DEMO-{index:03d}"
                if Product.objects.filter(sku=sku).exists():
                    continue
                product = Product(
                    name=entry["name"],
                    slug=f"demo-{entry['slug']}",
                    sku=sku,
                    short_description=entry["short_description"],
                    description=f"{entry['description']}\n\n{DEMO_NOTICE}",
                    price=entry["price"],
                    stock=entry["stock"],
                    status="published",
                    purchasable=True,
                    sort_order=index,
                )
                product.full_clean()
                product.save()
                product.categories.add(categories[entry["category"]])
                ProductAttribute.objects.bulk_create(
                    [
                        ProductAttribute(product=product, name=name, value=value, sort_order=order)
                        for order, (name, value) in enumerate(entry["attributes"])
                    ]
                )
                ProductImage.objects.create(
                    product=product,
                    image=ContentFile(images[entry["image"]], name=f"{sku.lower()}.webp"),
                    alt=f"Демонстрационная визуализация: {entry['name']}",
                )
                created_count += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Добавлено {created_count} демотоваров. Существующие товары сохранены. "
                f"Каталог: {settings.SHOP_ORIGIN}/ — оформление и оплата выключены."
            )
        )
