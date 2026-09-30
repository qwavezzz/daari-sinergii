from .models import DeliveryMethod


def default_delivery():
    return DeliveryMethod.objects.filter(active=True).order_by("-is_default", "sort_order", "pk").first()
