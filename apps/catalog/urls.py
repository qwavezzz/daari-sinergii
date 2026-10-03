from django.urls import path
from . import views
from apps.content.customer_views import page as customer_page

app_name = "catalog"
urlpatterns = [
    path("", views.index, name="index"),
    path("products/<slug:slug>/", views.product, name="product"),
    path("product-images/<str:filename>/", views.product_image, name="image"),
    path("delivery-and-payment/", customer_page, {"slug": "delivery"}, name="conditions"),
    path("legal/<slug:slug>/", customer_page, name="legal"),
]
