import uuid
from django.conf import settings
from django.http import HttpResponseBadRequest
from django.utils.cache import patch_vary_headers
from .seo import PRIVATE_PATHS, should_noindex


class HostRoutingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()
        if host == settings.SHOP_HOST:
            request.urlconf = "config.shop_urls"
            request.is_shop = True
        elif host in {settings.MAIN_HOST, "www." + settings.MAIN_HOST} or (
            settings.DEBUG and host in {"127.0.0.1", "testserver", "["}
        ):
            request.urlconf = "config.main_urls"
            request.is_shop = False
        else:
            return HttpResponseBadRequest("Неизвестный домен")
        request.request_id = uuid.uuid4().hex
        return self.get_response(request)


class ResponsePolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = None
        if request.method == "POST" and request.path == "/admin/login/":
            from .ratelimit import allow_request

            if not allow_request(request, "admin-login", limit=5, seconds=60):
                from django.http import HttpResponse

                response = HttpResponse(
                    "Слишком много попыток входа. Повторите через минуту.",
                    status=429,
                    headers={"Retry-After": "60", "Cache-Control": "no-store"},
                )
        if response is None:
            response = self.get_response(request)
        patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
        response["X-Request-ID"] = getattr(request, "request_id", "")
        image_origin = settings.MAIN_ORIGIN if getattr(request, "is_shop", False) else ""
        response.setdefault(
            "Content-Security-Policy",
            (
                f"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: {image_origin}; media-src 'self'; font-src 'self'; connect-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
            ),
        )
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if should_noindex(request) or response.status_code >= 400:
            response["X-Robots-Tag"] = "noindex, nofollow"
        if request.path.startswith(PRIVATE_PATHS):
            response["Cache-Control"] = "no-store, private"
        elif response.get("Content-Type", "").startswith("text/html"):
            response["Cache-Control"] = "no-cache, private"
        return response
