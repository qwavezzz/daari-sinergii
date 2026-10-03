from decimal import Decimal
import uuid
import json
import re
from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.crypto import salted_hmac
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from apps.cart.services import cart_context, get_cart
from apps.core.http import navigation_redirect, render_page
from apps.core.ratelimit import allow_request
from .forms import CheckoutForm
from .models import Order, DeliveryMethod
from .services import QuoteChanged, checkout_is_enabled, checkout_snapshot, create_order


def checkout_context(cart, context, form, method):
    from .cdek import configured, DeliveryUnavailable
    from .map_config import map_config
    from .shipping import packages_for, verified_delivery

    delivery_price = context["delivery_quotes"].get(method.pk) if method else None
    context["delivery_requires_address"] = bool(
        method and method.type == "static" and method.address_required
    )
    context["cdek_selected"] = bool(method and method.type == "cdek_pvz")
    form.fields["address"].required = context["delivery_requires_address"]
    context["cdek_ready"] = configured()
    context["cdek_map"] = map_config() if configured() else {}
    context["cdek_test_mode"] = getattr(settings, "CDEK_TEST_MODE", True)
    context["cdek_quote_ttl"] = getattr(settings, "CDEK_QUOTE_TTL_SECONDS", 900)
    context["cdek_default_city"] = settings.CDEK_FROM_CITY_CODE
    if context["cdek_selected"]:
        try:
            if not configured():
                raise DeliveryUnavailable("Расчёт СДЭК пока не подключён. Товары сохранятся в корзине.")
            if not method.cdek_tariff_code:
                raise DeliveryUnavailable("Тариф СДЭК ещё не настроен. Свяжитесь с магазином.")
            packages_for(cart)
        except DeliveryUnavailable as exc:
            context["cdek_unavailable"] = " ".join(exc.messages)
            context["cdek_ready"] = False
        if form["delivery_quote"].value():
            try:
                shipping = verified_delivery(
                    cart, method, form["delivery_quote"].value(), form["pvz_code"].value()
                )
            except ValidationError:
                pass
            else:
                context["shipping"] = shipping
                delivery_price = Decimal(shipping["price"])
    context.update(
        {
            "form": form,
            "checkout_enabled": checkout_is_enabled(),
            "delivery_price": delivery_price,
            "order_total": context["cart_total"] + delivery_price if delivery_price is not None else None,
            "page_title": "Оформление заказа — Дары Синергии",
        }
    )
    return context


@require_http_methods(["GET", "POST"])
def checkout(request):
    cart = get_cart(request)
    if not cart:
        return navigation_redirect(request, "/cart/")
    context, current_quote = checkout_snapshot(cart)
    status = 200
    if request.method == "POST":
        if not allow_request(request, "checkout", 20, 60):
            return HttpResponse("Слишком много попыток. Повторите через минуту.", status=429)
        method_id = request.POST.get("delivery_method", "")
        method = (
            DeliveryMethod.objects.filter(pk=method_id, active=True).first() if method_id.isdigit() else None
        )
        if request.POST.get("requote") == "1" or request.POST.get("shipping_requote") == "1":
            initial = request.POST.dict()
            initial.update(
                quote_token=current_quote, confirmed_delivery=method.pk if method else "", delivery_quote=""
            )
            if request.POST.get("shipping_requote") == "1" and method:
                from .shipping import quote_delivery

                try:
                    result = quote_delivery(
                        cart, method, request.POST.get("pvz_code", ""), request.session.session_key
                    )
                    initial.update(delivery_quote=result["delivery_quote"], quote_token=result["quote_token"])
                except ValidationError as exc:
                    context["error"] = " ".join(exc.messages)
                    status = 422
            form = CheckoutForm(initial=initial)
        else:
            form = CheckoutForm(request.POST)
            if form.is_valid():
                method = form.cleaned_data["delivery_method"]
                if form.cleaned_data.get("confirmed_delivery") != method.pk:
                    updated = request.POST.copy()
                    updated["confirmed_delivery"] = str(method.pk)
                    form.data = updated
                else:
                    try:
                        order = create_order(cart, form.cleaned_data, request.session.session_key)
                    except ValidationError as exc:
                        form.add_error(None, exc)
                        status = 422
                        if isinstance(exc, QuoteChanged):
                            context, current_quote = checkout_snapshot(cart)
                            method.refresh_from_db()
                            updated = request.POST.copy()
                            updated.update(
                                quote_token=current_quote,
                                delivery_quote="",
                                confirmed_delivery=str(method.pk) if method.active else "",
                            )
                            form.data = updated
                    else:
                        response = proceed_to_payment(request, order)
                        actual_cart = cart_context(cart)
                        response["HX-Trigger"] = json.dumps(
                            {
                                "cart-updated": {
                                    "count": actual_cart["cart_count"],
                                    "version": actual_cart["cart_version"],
                                }
                            }
                        )
                        response["X-Cart-Version"] = str(actual_cart["cart_version"])
                        return response
            else:
                status = 422
    else:
        if not context["cart_items"]:
            return navigation_redirect(request, "/cart/")
        method = context["cart_delivery_method"]
        form = CheckoutForm(
            initial={
                "checkout_key": uuid.uuid4(),
                "quote_token": current_quote,
                "delivery_method": method.pk if method else "",
                "confirmed_delivery": method.pk if method else "",
            }
        )
    context = checkout_context(cart, context, form, method)
    return render_page(request, "shop/checkout.html", "shop/partials/checkout_content.html", context, status)


@require_POST
def cdek_quote(request):
    from .shipping import quote_delivery
    from .services import quote_data

    if not allow_request(request, "cdek-quote", 12, 60):
        return JsonResponse({"message": "Слишком много расчётов. Повторите через минуту."}, status=429)
    cart = get_cart(request)
    if not cart or not checkout_is_enabled():
        return JsonResponse(
            {"message": "Добавьте товары в корзину или повторите оформление позже."}, status=400
        )
    method_id = request.POST.get("delivery_method", "")
    method = (
        DeliveryMethod.objects.filter(pk=method_id, active=True, type="cdek_pvz").first()
        if re.fullmatch(r"[0-9]{1,9}", method_id)
        else None
    )
    if not method:
        return JsonResponse({"message": "Выберите доступную доставку СДЭК."}, status=400)
    try:
        presented = signing.loads(request.POST.get("quote_token", ""), salt="checkout-quote", max_age=3600)
        if presented != quote_data(cart):
            raise signing.BadSignature()
    except signing.BadSignature:
        return JsonResponse(
            {"message": "Корзина или условия изменились. Обновите страницу оформления и повторите расчёт."},
            status=422,
        )
    try:
        result = quote_delivery(cart, method, request.POST.get("pvz_code", ""), request.session.session_key)
    except ValidationError as exc:
        return JsonResponse({"message": " ".join(exc.messages)}, status=422)
    response = JsonResponse(result)
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def cdek_map_points(request):
    page = request.GET.get("page", "0")
    if not re.fullmatch(r"[0-9]{1,3}", page) or int(page) > 199:
        return JsonResponse({"message": "Проверьте страницу справочника."}, status=400)
    return cdek_directory(request, "map_points", int(page))


def cdek_directory(request, operation, *args):
    from .cdek import CdekClient

    cart = get_cart(request)
    if not cart or not cart.items.exists() or not checkout_is_enabled():
        return JsonResponse({"message": "Откройте оформление заказа из корзины."}, status=403)
    if not allow_request(request, "cdek-directory", 240 if operation == "map_points" else 40, 60):
        return JsonResponse({"message": "Повторите поиск через минуту."}, status=429)
    try:
        client = CdekClient()  # Check configuration before returning cached provider data.
        key = (
            "cdek-directory:v3:"
            + salted_hmac("cdek-directory", str([client.token_key, operation, args])).hexdigest()
        )
        result = cache.get(key)
        if result is None:
            # Network operations run after allow_request has released its transaction.
            result = getattr(client, operation)(*args)
            cache.set(key, result, 300)
    except ValidationError as exc:
        return JsonResponse({"message": " ".join(exc.messages)}, status=503)
    response = JsonResponse(result)
    response["Cache-Control"] = "no-store"
    return response


def owned_order(request, public_id):
    # An unguessable public UUID supplements, and never replaces, ownership.
    return get_object_or_404(
        Order.objects.prefetch_related("items", "payment_attempts"),
        public_id=public_id,
        session_key=request.session.session_key or "",
    )


@require_GET
def detail(request, public_id):
    order = owned_order(request, public_id)
    trial = getattr(order, "trial_payment", None)

    return render_page(
        request,
        "shop/order.html",
        "shop/partials/order_content.html",
        {
            "order": order,
            "trial_payment": trial,
            "page_title": "Ваш заказ — Дары Синергии",
            "payment_enabled": settings.ALFABANK_ENABLED
            and not trial
            and order.financial_status in {"unpaid", "pending"}
            and order.status != "canceled"
            and not order.needs_attention,
        },
    )


@require_POST
def pay(request, public_id):
    order = owned_order(request, public_id)
    if not allow_request(request, "payment", 8, 60):
        return HttpResponse("Слишком много попыток. Повторите через минуту.", status=429)
    return proceed_to_payment(request, order)


def proceed_to_payment(request, order):
    """Checkout and retry share the same persisted, idempotent payment operation."""
    order_url = order.get_absolute_url()
    trial = getattr(order, "trial_payment", None)
    if trial:
        destination = trial.get_absolute_url() if settings.PAYMENT_STUB_ENABLED else order_url
        return navigation_redirect(request, destination)
    if (
        not settings.ALFABANK_ENABLED
        or order.needs_attention
        or order.financial_status not in {"unpaid", "pending"}
        or order.status == "canceled"
    ):
        return navigation_redirect(request, order_url)
    from apps.payments.services import start_payment
    from apps.payments.provider import PaymentError

    try:
        attempt = start_payment(order.pk)
    except (PaymentError, ValidationError) as exc:
        messages.error(request, str(exc))
        return navigation_redirect(request, order_url)
    destination = (
        attempt.confirmation_url
        if attempt.state in {"pending", "waiting_for_capture"} and attempt.confirmation_url
        else order_url
    )
    return navigation_redirect(request, destination)


@require_POST
def refresh_payment(request, public_id):
    order = owned_order(request, public_id)
    if not allow_request(request, "payment-refresh", 15, 60):
        return HttpResponse(status=429)
    from apps.payments.services import reconcile_attempt
    from apps.payments.provider import PaymentError

    for attempt in order.payment_attempts.exclude(state="canceled"):
        try:
            reconcile_attempt(attempt.pk)
        except PaymentError:
            messages.info(request, "Платёж пока не удалось проверить. Мы продолжим проверку автоматически.")
    return navigation_redirect(request, order.get_absolute_url())
