from django.urls import path
from .views import webhook
from .trial_views import trial_action, trial_page

app_name = "payments"
urlpatterns = [
    path("alfabank/webhook/", webhook, name="webhook"),
    path("trial/<uuid:public_id>/", trial_page, name="trial"),
    path("trial/<uuid:public_id>/action/", trial_action, name="trial_action"),
]
