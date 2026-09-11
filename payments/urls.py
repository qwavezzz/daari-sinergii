from django.urls import path
from .views import webhook

app_name = "payments"
urlpatterns = [path("yookassa/webhook/", webhook, name="webhook")]
