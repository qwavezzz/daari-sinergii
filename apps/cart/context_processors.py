from .services import cart_context, get_cart


def cart_summary(request):
    if not getattr(request, "is_shop", False) or request.path.startswith("/admin/"):
        return {}
    return cart_context(get_cart(request))
