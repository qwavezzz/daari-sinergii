from django.urls import path
from .customer_content import CUSTOMER_PAGES
from .customer_views import page

app_name = "customers"
urlpatterns = [path(row[1].lstrip("/"), page, {"slug": key}, name=key) for key, row in CUSTOMER_PAGES.items()]
