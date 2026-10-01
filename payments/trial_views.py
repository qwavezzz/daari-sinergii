from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from core.http import navigation_redirect, render_page
from core.ratelimit import allow_request
from .models import TrialPayment
from .trial import apply_trial_action


def owned_trial(request, public_id):
    if not getattr(settings, "PAYMENT_STUB_ENABLED", False) or not request.session.session_key:
        raise Http404
    return get_object_or_404(
        TrialPayment.objects.select_related("order"),
        order__public_id=public_id,
        order__session_key=request.session.session_key,
    )


def trial_response(request, trial, *, error="", status=200):
    return render_page(
        request,
        "payments/trial.html",
        "shop/partials/trial_payment.html",
        {
            "trial": trial,
            "order": trial.order,
            "snapshot": trial.snapshot,
            "error": error,
            "page_title": "Пробная оплата без списания — Дары Синергии",
            "noindex": True,
            "can_simulate": trial.order.status == "new"
            and trial.order.financial_status == "unpaid"
            and not trial.order.needs_attention,
        },
        status=status,
    )


@never_cache
@require_GET
def trial_page(request, public_id):
    return trial_response(request, owned_trial(request, public_id))


@never_cache
@require_POST
@csrf_protect
def trial_action(request, public_id):
    trial = owned_trial(request, public_id)
    if not allow_request(request, "trial-payment", 30, 60):
        return HttpResponse("Слишком много попыток. Повторите через минуту.", status=429)
    if request.POST.get("action") not in {"success", "cancel", "retry"} or not request.POST.get("action_key"):
        return trial_response(
            request, trial, error="Обновите страницу и выберите действие пробы.", status=400
        )
    try:
        trial = apply_trial_action(
            trial.order_id,
            request.session.session_key,
            request.POST["action"],
            request.POST["action_key"],
        )
    except ValidationError as exc:
        return trial_response(request, trial, error=" ".join(exc.messages), status=409)
    return navigation_redirect(request, trial.get_absolute_url())
