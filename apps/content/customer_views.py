from django.conf import settings
from django.http import Http404
from django.views.decorators.http import require_GET
from apps.core.http import render_page
from apps.orders.models import StoreSettings, DeliveryMethod
from .models import Document, FAQEntry, SiteSettings
from .customer_content import (
    CUSTOMER_PAGES,
    customer_sales_available,
    render_customer_text,
    seller_details,
    text_blocks,
    text_values,
)


@require_GET
def page(request, slug):
    if slug not in CUSTOMER_PAGES:
        raise Http404
    title, path, field = CUSTOMER_PAGES[slug]
    store = StoreSettings.objects.filter(pk=1).first()
    values = text_values()
    site = SiteSettings.objects.first()
    context = {
        "customer_page": slug,
        "customer_title": title,
        "customer_blocks": text_blocks(render_customer_text(getattr(store, field, ""), values)),
        "customer_updated_at": store.updated_at if store else None,
        "customer_is_shop": getattr(request, "is_shop", False),
        "page_title": title + " — Дары Синергии",
        "page_description": title + " интернет-магазина «Дары Синергии»: информация для покупателей.",
        "canonical_url": settings.MAIN_ORIGIN + path,
        "seller_details": seller_details(site),
        "customer_sales_available": customer_sales_available(store),
        "customer_seller_incomplete": not site
        or not all(
            getattr(site, name).strip()
            for name in ("legal_name", "inn", "registration_number", "address", "return_address")
        ),
        "customer_base": "shop/base.html" if getattr(request, "is_shop", False) else "site/base.html",
    }
    if slug == "documents":
        context["declarations"] = Document.objects.published().filter(is_declaration=True)
    elif slug == "faq":
        context["faq_entries"] = [
            {"question": entry.question, "answer": render_customer_text(entry.answer, values)}
            for entry in FAQEntry.objects.filter(active=True)
        ]
    elif slug == "delivery":
        context["delivery_methods"] = DeliveryMethod.objects.filter(active=True).order_by(
            "-is_default", "sort_order", "pk"
        )
    return render_page(request, "customer/page.html", "customer/content.html", context)
