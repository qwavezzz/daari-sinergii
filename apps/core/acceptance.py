"""Recorded external evidence is separate from automated checks; never inferred."""

import hashlib
import json

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

from apps.catalog.models import Product, ProductAttribute, ProductImage
from apps.content.models import SiteSettings
from apps.orders.models import (
    DeliveryMethod,
    NotificationSettings,
    PackingBox,
    PackingRecipe,
    PackingRecipeItem,
    StoreSettings,
)


def configuration_digest(check):
    data = {"schema": 1, "host": settings.SHOP_ORIGIN}
    groups = {
        "shipping": [
            "CDEK_ENABLED",
            "CDEK_TEST_MODE",
            "CDEK_CLIENT_ID",
            "CDEK_CLIENT_SECRET",
            "CDEK_FROM_CITY_CODE",
            "CDEK_FROM_PVZ_CODE",
            "CDEK_DEMO_QUOTES_ENABLED",
        ],
        "email": [
            "EMAIL_HOST",
            "EMAIL_PORT",
            "EMAIL_HOST_USER",
            "EMAIL_HOST_PASSWORD",
            "EMAIL_USE_TLS",
            "EMAIL_USE_SSL",
            "DEFAULT_FROM_EMAIL",
            "MANAGER_EMAIL",
            "EMAIL_REPLY_TO",
        ],
        "payment": [
            "ALFABANK_ENABLED",
            "ALFABANK_TEST_MODE",
            "ALFABANK_USERNAME",
            "ALFABANK_PASSWORD",
            "PAYMENT_STUB_ENABLED",
        ],
        "fiscal": ["ALFABANK_RECEIPT_MODE", "ALFABANK_TAX_SYSTEM", "ALFABANK_USERNAME", "ALFABANK_TEST_MODE"],
    }
    data["settings"] = {name: getattr(settings, name) for name in groups.get(check, [])}
    if check in {"catalog", "shipping", "fiscal"}:
        fields = [
            f.name
            for f in Product._meta.fields
            if f.name not in {"created_at", "updated_at", "stock", "reserved_stock"}
        ]
        data["products"] = list(Product.objects.filter(status="published").order_by("pk").values(*fields))
        data["delivery"] = list(DeliveryMethod.objects.filter(active=True).order_by("pk").values())
    if check == "shipping":
        for model in (PackingBox, PackingRecipe, PackingRecipeItem):
            data[model.__name__] = list(model.objects.order_by("pk").values())
    if check == "catalog":
        data["seller"] = list(SiteSettings.objects.order_by("pk").values())
        data["store"] = list(StoreSettings.objects.order_by("pk").values())
        data["attributes"] = list(ProductAttribute.objects.order_by("pk").values())
        data["images"] = list(ProductImage.objects.order_by("pk").values())
    if check == "email":
        data["notification"] = list(NotificationSettings.objects.order_by("pk").values())
    if check in {"checkout", "operations"}:
        data["release"] = str(settings.BASE_DIR.name)
    return hashlib.sha256(json.dumps(data, sort_keys=True, cls=DjangoJSONEncoder).encode()).hexdigest()
