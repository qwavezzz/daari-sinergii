from decimal import Decimal
from django import template

register = template.Library()


@register.filter
def money(value):
    if value is None or value == "":
        return ""
    amount = Decimal(str(value))
    result = f"{amount:,.2f}".replace(",", "\u00a0").replace(".", ",")
    return result[:-3] if result.endswith(",00") else result


@register.filter
def ru_products(value):
    quantity = abs(int(value or 0))
    if quantity % 100 in range(11, 15):
        return "товаров"
    return {1: "товар", 2: "товара", 3: "товара", 4: "товара"}.get(quantity % 10, "товаров")
