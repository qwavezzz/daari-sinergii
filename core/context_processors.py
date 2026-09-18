from django.conf import settings
from .seo import has_demo_catalog, should_noindex


def public_settings(request):
    from orders.services import checkout_is_enabled

    demo_catalog = has_demo_catalog(request)
    return {
        "demo_catalog": demo_catalog,
        "main_origin": settings.MAIN_ORIGIN,
        "shop_origin": settings.SHOP_ORIGIN,
        "site_url": settings.MAIN_ORIGIN,
        "shop_url": settings.SHOP_ORIGIN,
        "noindex": should_noindex(request),
        "checkout_enabled": checkout_is_enabled() if getattr(request, "is_shop", False) else False,
        "payment_enabled": settings.YOOKASSA_ENABLED,
    }
