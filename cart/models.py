from django.db import models
from core.models import TimeStampedModel


class Cart(TimeStampedModel):
    session_key = models.CharField(max_length=40, unique=True)
    version = models.PositiveBigIntegerField(default=0)

    class Meta:
        verbose_name = "Корзина"
        verbose_name_plural = "Корзины"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField("Количество")

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="one_product_per_cart"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="cart_quantity_positive"),
        ]
