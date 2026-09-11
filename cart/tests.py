from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from cart.models import CartItem
from cart.services import cart_context, mutate_cart
from orders.test_support import fixture_cart


class CartTests(TestCase):
    def setUp(self):
        self.cart, self.product, self.method = fixture_cart()

    def test_repeated_add_and_update_are_authoritative(self):
        mutate_cart(self.cart, "add", 2, product_id=self.product.pk)
        self.assertEqual(self.cart.items.get().quantity, 3)
        mutate_cart(self.cart, "update", 2, item_id=self.cart.items.get().pk)
        snapshot = cart_context(self.cart)
        self.assertEqual(snapshot["cart_total"], 200)
        self.assertEqual(snapshot["cart_version"], 2)

    def test_invalid_stock_does_not_mutate_cart(self):
        with self.assertRaises(ValidationError):
            mutate_cart(self.cart, "add", 9, product_id=self.product.pk)
        self.assertEqual(self.cart.items.get().quantity, 1)

    def test_mutations_are_post_csrf_protected(self):
        client = Client(enforce_csrf_checks=True, HTTP_HOST="shop.localhost")
        url = f"/cart/add/{self.product.pk}/"
        self.assertEqual(client.get(url).status_code, 405)
        self.assertEqual(client.post(url, {"quantity": 1}).status_code, 403)

    def test_cart_item_is_session_owned(self):
        client = Client(HTTP_HOST="shop.localhost")
        response = client.post(f"/cart/update/{self.cart.items.get().pk}/", {"quantity": 2})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.cart.items.get().quantity, 1)

    def test_hidden_product_cannot_be_added(self):
        self.product.status = "draft"
        self.product.save()
        response = self.client.post(
            f"/cart/add/{self.product.pk}/", {"quantity": 1}, HTTP_HOST="shop.localhost"
        )
        self.assertEqual(response.status_code, 404)

    def test_htmx_response_exposes_current_version(self):
        client = Client(HTTP_HOST="shop.localhost")
        response = client.post(
            f"/cart/add/{self.product.pk}/", {"quantity": 2, "price": "0.01"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Cart-Version"], "1")
        self.assertIn("cart-updated", response["HX-Trigger"])
        self.assertEqual(CartItem.objects.get(cart__session_key=client.session.session_key).quantity, 2)
