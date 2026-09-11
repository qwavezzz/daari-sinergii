import json
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.views.decorators.http import require_GET, require_POST
from core.http import is_partial, render_page
from .forms import QuantityForm
from .services import cart_context, get_cart, mutate_cart


def response_for_cart(request, cart, error="", status=200):
    context = cart_context(cart)
    context["cart_error"] = error
    drawer = (
        request.method == "POST"
        or request.GET.get("drawer") == "1"
        or request.headers.get("X-Cart-Drawer") == "true"
    )
    partial = "shop/partials/cart_content.html" if drawer else "shop/partials/cart_page_content.html"
    response = render_page(request, "shop/cart.html", partial, context, status=status)
    response["X-Cart-Version"] = str(context["cart_version"])
    response["HX-Trigger"] = json.dumps(
        {"cart-updated": {"count": context["cart_count"], "version": context["cart_version"]}}
    )
    return response


@require_GET
def detail(request):
    return response_for_cart(request, get_cart(request))


@require_POST
def mutation(request, operation, product_id=None, item_id=None):
    cart = get_cart(request, create=True)
    form = QuantityForm(request.POST)
    error = ""
    if operation != "remove" and not form.is_valid():
        error = "Укажите целое количество от 1 до 999."
    else:
        try:
            cart = mutate_cart(
                cart,
                operation,
                form.cleaned_data.get("quantity", 1) if operation != "remove" else 1,
                product_id,
                item_id,
            )
        except ValidationError as exc:
            error = " ".join(exc.messages)
    if is_partial(request):
        return response_for_cart(request, cart, error, status=422 if error else 200)
    if error:
        messages.error(request, error)
    return redirect("cart:detail")
