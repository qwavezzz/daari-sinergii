from django.urls import path
from . import views

app_name = "orders"
urlpatterns = [
    path("checkout/", views.checkout, name="checkout"),
    path("orders/<uuid:public_id>/", views.detail, name="detail"),
    path("orders/<uuid:public_id>/pay/", views.pay, name="pay"),
    path("orders/<uuid:public_id>/refresh/", views.refresh_payment, name="refresh"),
]
