from django.urls import path
from .views import webhook

app_name = "payments"
urlpatterns = [
    path("yookassa/webhook/", webhook, {"test_mode": False}, name="webhook"),
    path("yookassa/test/webhook/", webhook, {"test_mode": True}, name="test_webhook"),
]
