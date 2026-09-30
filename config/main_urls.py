from django.urls import include, path
from core.views import health, robots, sitemap

urlpatterns = [
    path("health/", health),
    path("robots.txt", robots),
    path("sitemap.xml", sitemap),
    path("", include("content.customer_urls")),
    path("", include("content.urls")),
]
