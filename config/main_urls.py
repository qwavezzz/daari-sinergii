from django.urls import include, path
from apps.core.views import health, robots, sitemap

urlpatterns = [
    path("health/", health),
    path("robots.txt", robots),
    path("sitemap.xml", sitemap),
    path("", include("apps.content.customer_urls")),
    path("", include("apps.content.urls")),
]
