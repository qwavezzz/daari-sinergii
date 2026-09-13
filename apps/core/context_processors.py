from django.conf import settings


def public_settings(request):
    from apps.catalog.models import Product
    from apps.orders.services import checkout_is_enabled

    demo_catalog = (
        getattr(request, "is_shop", False)
        and Product.objects.filter(sku__startswith="DEMO-", status="published").exists()
    )
    return {
        "demo_catalog": demo_catalog,
        "main_origin": settings.MAIN_ORIGIN,
        "shop_origin": settings.SHOP_ORIGIN,
        "site_url": settings.MAIN_ORIGIN,
        "shop_url": settings.SHOP_ORIGIN,
        "noindex": demo_catalog
        or request.path.startswith(
            ("/cart/", "/checkout/", "/orders/", "/admin/", "/payments/", "/preview/")
        ),
        "checkout_enabled": checkout_is_enabled() if getattr(request, "is_shop", False) else False,
        "payment_enabled": settings.YOOKASSA_ENABLED,
        "test_payments": settings.YOOKASSA_ENABLED and settings.YOOKASSA_TEST_MODE,
    }
