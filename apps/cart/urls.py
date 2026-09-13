from django.urls import path
from . import views

app_name = "cart"
urlpatterns = [
    path("", views.detail, name="detail"),
    path("add/<int:product_id>/", views.mutation, {"operation": "add"}, name="add"),
    path("update/<int:item_id>/", views.mutation, {"operation": "update"}, name="update"),
    path("remove/<int:item_id>/", views.mutation, {"operation": "remove"}, name="remove"),
]
