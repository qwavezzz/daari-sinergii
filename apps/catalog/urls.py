from django.urls import path
from . import views

app_name = "catalog"
urlpatterns = [
    path("", views.index, name="index"),
    path("products/<slug:slug>/", views.product, name="product"),
    path("product-images/<str:filename>/", views.product_image, name="image"),
    path("delivery-and-payment/", views.conditions, name="conditions"),
    path("legal/<slug:slug>/", views.legal, name="legal"),
]
