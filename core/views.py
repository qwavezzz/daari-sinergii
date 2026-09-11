from xml.sax.saxutils import escape
from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


@require_GET
def robots(request):
    origin = settings.SHOP_ORIGIN if request.is_shop else settings.MAIN_ORIGIN
    return HttpResponse(
        "User-agent: *\nDisallow: /admin/\nDisallow: /cart/\nDisallow: /checkout/\nDisallow: /orders/\nDisallow: /payments/\nDisallow: /preview/\nSitemap: "
        + origin
        + "/sitemap.xml\n",
        content_type="text/plain",
    )


@require_GET
def sitemap(request):
    if request.is_shop:
        from catalog.models import Product

        paths = ["/"] + [
            f"/products/{slug}/"
            for slug in Product.objects.filter(status="published").values_list("slug", flat=True)
        ]
        origin = settings.SHOP_ORIGIN
    else:
        from content.models import Collection

        paths = ["/", "/materials/"] + [
            f"/materials/{slug}/" for slug in Collection.objects.published().values_list("slug", flat=True)
        ]
        origin = settings.MAIN_ORIGIN
    body = "".join(f"<url><loc>{escape(origin + path)}</loc></url>" for path in paths)
    return HttpResponse(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + body
        + "</urlset>",
        content_type="application/xml",
    )
