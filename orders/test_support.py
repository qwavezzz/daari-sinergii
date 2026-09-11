import uuid
from decimal import Decimal
from catalog.models import Product
from cart.models import Cart, CartItem
from orders.models import DeliveryMethod, StoreSettings
from orders.services import sign_quote


def fixture_cart(session_key="test-owner", stock=5, quantity=1):
    StoreSettings.objects.update_or_create(
        pk=1,
        defaults={
            "checkout_enabled": True,
            "terms_text": "Утверждённые тестовые условия",
            "privacy_text": "Тестовая политика",
        },
    )
    method, _ = DeliveryMethod.objects.get_or_create(
        slug="test-pickup",
        defaults={
            "name": "Тестовое получение",
            "price": Decimal("50.00"),
            "address_required": False,
            "active": True,
        },
    )
    product = Product.objects.create(
        name="Тестовый товар",
        sku=str(uuid.uuid4()),
        slug=str(uuid.uuid4()),
        price=Decimal("100.00"),
        stock=stock,
        purchasable=True,
        status="published",
    )
    cart = Cart.objects.create(session_key=session_key)
    CartItem.objects.create(cart=cart, product=product, quantity=quantity)
    return cart, product, method


def checkout_data(cart, method, **overrides):
    return {
        "checkout_key": uuid.uuid4(),
        "quote_token": sign_quote(cart),
        "name": "Тестовый покупатель",
        "phone": "+79990000000",
        "email": "buyer@example.test",
        "delivery_method": method,
        "address": "",
        "comment": "",
        "accept_terms": True,
        "confirmed_delivery": method.pk,
        **overrides,
    }
