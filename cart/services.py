from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from catalog.models import Product
from .models import Cart, CartItem


def get_cart(request, create=False):
    if not request.session.session_key:
        if not create:
            return None
        request.session.create()
    if create:
        return Cart.objects.get_or_create(session_key=request.session.session_key)[0]
    return Cart.objects.filter(session_key=request.session.session_key).first()


def cart_context(cart):
    items, total, count = [], Decimal("0.00"), 0
    if cart:
        cart.refresh_from_db()
        for item in cart.items.select_related("product").prefetch_related("product__images"):
            product = item.product
            subtotal = (product.price or Decimal("0")) * item.quantity
            items.append(
                {
                    "item": item,
                    "product": product,
                    "quantity": item.quantity,
                    "unit_price": product.price,
                    "subtotal": subtotal,
                    "available": product.is_available and item.quantity <= product.available_quantity,
                }
            )
            total += subtotal
            count += item.quantity
    return {
        "cart": cart,
        "cart_items": items,
        "cart_total": total,
        "cart_count": count,
        "cart_version": cart.version if cart else 0,
        "cart_valid": bool(items) and all(item["available"] for item in items),
    }


@transaction.atomic
def mutate_cart(cart, operation, quantity=1, product_id=None, item_id=None):
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    if operation == "add":
        product = get_object_or_404(Product, pk=product_id, status="published")
        item = cart.items.filter(product=product).first()
        new_quantity = quantity + (item.quantity if item else 0)
    else:
        item = get_object_or_404(CartItem.objects.select_related("product"), pk=item_id, cart=cart)
        product, new_quantity = item.product, quantity
    if operation == "remove":
        item.delete()
    else:
        if not product.is_available or not 1 <= new_quantity <= min(product.available_quantity, 999):
            raise ValidationError("Товар недоступен в выбранном количестве. Обновите корзину.")
        CartItem.objects.update_or_create(cart=cart, product=product, defaults={"quantity": new_quantity})
    cart.version += 1
    cart.save(update_fields=["version", "updated_at"])
    return cart
