"""Structured data for public information pages, using editable company details."""

import json

from django.conf import settings
from django.templatetags.static import static

from core.seo import site_is_indexable

from .models import SiteSettings


def absolute_main_url(path):
    return settings.MAIN_ORIGIN.rstrip("/") + "/" + path.lstrip("/")


def schema_context(request, *, topic=None, materials=False):
    breadcrumbs = []
    data = None
    if materials:
        breadcrumbs = [
            {"name": "Главная", "url": absolute_main_url("/")},
            {"name": "Материалы", "url": absolute_main_url("/materials/")},
        ]
        if topic:
            breadcrumbs.append({"name": topic.title, "url": absolute_main_url(topic.get_absolute_url())})
        data = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": index, "name": item["name"], "item": item["url"]}
                for index, item in enumerate(breadcrumbs, 1)
            ],
        }
    else:
        company = SiteSettings.objects.first()
        if company and company.company_name.strip():
            data = {
                "@context": "https://schema.org",
                "@type": "Organization",
                "@id": absolute_main_url("/#organization"),
                "name": company.company_name,
                "url": absolute_main_url("/"),
                "logo": absolute_main_url(static("assets/brand-mark-navy-384.webp")),
            }
            for key, value in (
                ("legalName", company.legal_name),
                ("email", company.email),
                ("telephone", company.phone),
            ):
                if value.strip():
                    data[key] = value
    if not site_is_indexable(request):
        data = None
    return {
        "breadcrumbs": breadcrumbs,
        "structured_data": data,
        # An ordinary string: Django must HTML-escape this transport attribute.
        "structured_data_json": json.dumps(data, ensure_ascii=False) if data else "",
    }
