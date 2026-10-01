from django.contrib import admin
from django.urls import include, path
from apps.core.views import health, robots, sitemap

admin.site.site_header = "Дары Синергии"
admin.site.site_title = "Управление сайтом"
admin.site.index_title = "Рабочий стол"
urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
    path("robots.txt", robots),
    path("sitemap.xml", sitemap),
    path("", include("apps.content.customer_urls")),
    path("", include("apps.catalog.urls")),
    path("cart/", include("apps.cart.urls")),
    path("", include("apps.orders.urls")),
    path("payments/", include("apps.payments.urls")),
]
