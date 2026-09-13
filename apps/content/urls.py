from django.urls import path

from . import views

app_name = "content"

urlpatterns = [
    path("", views.home, name="home"),
    path("materials/", views.materials, name="materials"),
    path("materials/<slug:slug>/", views.materials, name="collection"),
    path("documents/<slug:slug>/", views.document, name="document"),
    path("documents/<path:path>", views.legacy_document, name="legacy_document"),
    path("media/reviews/<int:pk>/", views.review_photo, name="review_photo"),
    path("media/videos/<int:pk>/", views.video_cover, name="video_cover"),
]
