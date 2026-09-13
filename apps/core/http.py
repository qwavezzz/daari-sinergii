import json
from urllib.parse import urlsplit

from django.http import HttpResponse
from django.shortcuts import render, redirect


def is_partial(request):
    return (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )


def render_page(request, full_template, partial_template, context=None, status=200):
    context = dict(context or {})
    context.setdefault("canonical_url", request.build_absolute_uri(request.path))
    context.setdefault("page_title", "Дары Синергии")
    context.setdefault("page_description", "Системы озонирования воды, озонированные масла и гидролаты.")
    context.setdefault(
        "noindex",
        request.path.startswith(("/cart/", "/checkout/", "/orders/", "/admin/", "/payments/", "/preview/")),
    )
    return render(request, partial_template if is_partial(request) else full_template, context, status=status)


def navigation_redirect(request, url):
    if is_partial(request):
        parsed = urlsplit(str(url))
        if (
            not parsed.netloc
            and not parsed.scheme
            and str(url).startswith("/")
            and not str(url).startswith("//")
        ):
            return HttpResponse(
                status=200,
                headers={
                    "HX-Location": json.dumps(
                        {"path": str(url), "target": "#main-content", "swap": "innerHTML show:top"}
                    )
                },
            )
        return HttpResponse(status=200, headers={"HX-Redirect": str(url)})
    return redirect(url)
