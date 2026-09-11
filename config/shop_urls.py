from django.contrib import admin
from django.urls import include, path
from core.views import health, robots, sitemap

admin.site.site_header = "Дары Синергии"
admin.site.site_title = "Управление сайтом"
admin.site.index_title = "Сайт и магазин"
urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
    path("robots.txt", robots),
    path("sitemap.xml", sitemap),
    path("", include("catalog.urls")),
    path("cart/", include("cart.urls")),
    path("", include("orders.urls")),
    path("payments/", include("payments.urls")),
]
