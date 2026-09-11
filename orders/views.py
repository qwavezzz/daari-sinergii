import uuid
import json
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from cart.services import cart_context, get_cart
from core.http import navigation_redirect, render_page
from core.ratelimit import allow_request
from .forms import CheckoutForm
from .models import Order
from .services import QuoteChanged, checkout_is_enabled, checkout_snapshot, create_order


@require_http_methods(["GET", "POST"])
def checkout(request):
    cart = get_cart(request)
    if not cart:
        return navigation_redirect(request, "/cart/")
    context, current_quote = checkout_snapshot(cart)
    context["delivery_requires_address"] = False
    delivery_price = order_total = None
    if request.method == "POST" and request.POST.get("requote") == "1":
        from .models import DeliveryMethod

        method = (
            DeliveryMethod.objects.filter(pk=request.POST.get("delivery_method") or None, active=True).first()
            if (request.POST.get("delivery_method") or "").isdigit()
            else None
        )
        initial = request.POST.dict()
        initial["quote_token"] = current_quote
        initial["confirmed_delivery"] = method.pk if method else ""
        form = CheckoutForm(initial=initial)
        if method and method.pk in context["delivery_quotes"]:
            delivery_price = context["delivery_quotes"][method.pk]
            order_total = context["cart_total"] + delivery_price
            context["delivery_requires_address"] = method.address_required
            form.fields["address"].required = method.address_required
        context.update(
            {
                "form": form,
                "checkout_enabled": checkout_is_enabled(),
                "delivery_price": delivery_price,
                "order_total": order_total,
                "page_title": "Оформление заказа — Дары Синергии",
            }
        )
        return render_page(request, "shop/checkout.html", "shop/partials/checkout_content.html", context)
    if request.method == "POST":
        if not allow_request(request, "checkout", 10, 60):
            return HttpResponse("Слишком много попыток. Повторите через минуту.", status=429)
        form = CheckoutForm(request.POST)
        valid = form.is_valid()
        selected_method = form.cleaned_data.get("delivery_method")
        if selected_method:
            context["delivery_requires_address"] = selected_method.address_required
            form.fields["address"].required = selected_method.address_required
            delivery_price = context["delivery_quotes"].get(selected_method.pk)
            order_total = context["cart_total"] + delivery_price if delivery_price is not None else None
        if valid:
            method = form.cleaned_data["delivery_method"]
            delivery_price = context["delivery_quotes"].get(method.pk)
            order_total = context["cart_total"] + delivery_price if delivery_price is not None else None
            if form.cleaned_data.get("confirmed_delivery") != method.pk:
                updated = request.POST.copy()
                updated["confirmed_delivery"] = str(method.pk)
                form.data = updated
                context.update(
                    {
                        "form": form,
                        "checkout_enabled": checkout_is_enabled(),
                        "delivery_price": delivery_price,
                        "order_total": order_total,
                        "page_title": "Подтверждение заказа — Дары Синергии",
                    }
                )
                return render_page(
                    request, "shop/checkout.html", "shop/partials/checkout_content.html", context
                )
            try:
                order = create_order(cart, form.cleaned_data, request.session.session_key)
            except ValidationError as exc:
                form.add_error(None, exc)
                if isinstance(exc, QuoteChanged):
                    context, current_quote = checkout_snapshot(cart)
                    method.refresh_from_db()
                    context["delivery_requires_address"] = method.address_required
                    delivery_price = context["delivery_quotes"].get(method.pk)
                    order_total = (
                        context["cart_total"] + delivery_price if delivery_price is not None else None
                    )
                    updated = request.POST.copy()
                    updated["quote_token"] = current_quote
                    updated["confirmed_delivery"] = str(method.pk) if method.active else ""
                    # Keep entered values and a visible price-change error.
                    form.data = updated
            else:
                # create_order has committed before the external payment request starts.
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
        status = 422
    else:
        if not context["cart_items"]:
            return navigation_redirect(request, "/cart/")
        form = CheckoutForm(initial={"checkout_key": uuid.uuid4(), "quote_token": current_quote})
        status = 200
    context.update(
        {
            "form": form,
            "checkout_enabled": checkout_is_enabled(),
            "delivery_price": delivery_price,
            "order_total": order_total,
            "page_title": "Оформление заказа — Дары Синергии",
        }
    )
    return render_page(request, "shop/checkout.html", "shop/partials/checkout_content.html", context, status)


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

    return render_page(
        request,
        "shop/order.html",
        "shop/partials/order_content.html",
        {
            "order": order,
            "page_title": "Ваш заказ — Дары Синергии",
            "payment_enabled": settings.YOOKASSA_ENABLED
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
    if (
        not settings.YOOKASSA_ENABLED
        or order.needs_attention
        or order.financial_status not in {"unpaid", "pending"}
        or order.status == "canceled"
    ):
        return navigation_redirect(request, order_url)
    from payments.services import start_payment
    from payments.provider import PaymentError

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
    from payments.services import reconcile_attempt
    from payments.provider import PaymentError

    for attempt in order.payment_attempts.exclude(state="canceled"):
        try:
            reconcile_attempt(attempt.pk)
        except PaymentError:
            messages.info(request, "Платёж пока не удалось проверить. Мы продолжим проверку автоматически.")
    return navigation_redirect(request, order.get_absolute_url())
