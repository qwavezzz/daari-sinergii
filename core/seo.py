"""Shared indexing policy for HTML, fragments, HTTP headers and sitemaps."""

from django.conf import settings

PRIVATE_PATHS = ("/cart/", "/checkout/", "/orders/", "/admin/", "/payments/", "/preview/", "/health/")


def has_demo_catalog(request):
    if not hasattr(request, "_has_demo_catalog"):
        from catalog.models import Product

        request._has_demo_catalog = bool(
            getattr(request, "is_shop", False)
            and Product.objects.filter(sku__startswith="DEMO-", status="published").exists()
        )
    return request._has_demo_catalog


def site_is_indexable(request):
    if not settings.SITE_INDEXING_ENABLED:
        return False
    return not getattr(request, "is_shop", False) or (
        settings.SHOP_INDEXING_ENABLED and not has_demo_catalog(request)
    )


def should_noindex(request):
    return request.path.startswith(PRIVATE_PATHS) or not site_is_indexable(request)
