from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from core.http import render_page
from .models import Category, Product


@require_GET
def index(request):
    products = Product.objects.filter(status="published").prefetch_related("images", "categories")
    selected = None
    if request.GET.get("category"):
        selected = get_object_or_404(Category, slug=request.GET["category"], active=True)
        products = products.filter(categories=selected)
    context = {
        "products": Paginator(products, 12).get_page(request.GET.get("page")),
        "categories": Category.objects.filter(active=True),
        "selected_category": selected,
        "page_title": "Каталог — Дары Синергии",
        "canonical_url": request.build_absolute_uri("/"),
    }
    return render_page(request, "shop/catalog.html", "shop/partials/catalog_content.html", context)


@require_GET
def product(request, slug):
    item = get_object_or_404(
        Product.objects.prefetch_related("images", "attributes", "categories"), slug=slug, status="published"
    )
    context = {
        "product": item,
        "page_title": f"{item.name} — Дары Синергии",
        "page_description": item.short_description,
        "documents": item.documents.published(),
        "reviews": item.reviews.published(),
        "product_documents": item.documents.published(),
        "product_reviews": item.reviews.published(),
        "product_videos": item.videos.published(),
    }
    return render_page(request, "shop/product.html", "shop/partials/product_content.html", context)


@require_GET
def conditions(request):
    from orders.models import StoreSettings, DeliveryMethod

    return render_page(
        request,
        "shop/conditions.html",
        "shop/partials/conditions_content.html",
        {
            "store_settings": StoreSettings.objects.filter(pk=1).first(),
            "delivery_methods": DeliveryMethod.objects.filter(active=True),
            "page_title": "Получение и оплата — Дары Синергии",
        },
    )


@require_GET
def legal(request, slug):
    from django.http import Http404
    from orders.models import StoreSettings

    if slug not in {"terms", "privacy"}:
        raise Http404
    store = StoreSettings.objects.filter(pk=1).first()
    title = "Условия продажи" if slug == "terms" else "Политика обработки персональных данных"
    return render_page(
        request,
        "shop/legal.html",
        "shop/partials/legal_content.html",
        {
            "legal_title": title,
            "legal_text": getattr(store, "terms_text" if slug == "terms" else "privacy_text", ""),
            "page_title": title + " — Дары Синергии",
        },
    )


@require_GET
def product_image(request, filename):
    from django.http import FileResponse, Http404
    from .models import ProductImage

    picture = get_object_or_404(ProductImage, image="products/" + filename, product__status="published")
    try:
        response = FileResponse(picture.image.open("rb"))
    except FileNotFoundError as exc:
        raise Http404 from exc
    response["Cache-Control"] = "no-cache, private"
    response["X-Content-Type-Options"] = "nosniff"
    return response
