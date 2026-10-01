import json
import uuid

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.core.ratelimit import allow_request
from .models import PaymentAttempt
from .provider import InvalidPayment, PaymentError, safe_provider_id
from .services import reconcile_attempt


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    """A bank callback is an untrusted hint, never evidence that money moved."""
    if len(request.body) > 65536:
        return HttpResponse(status=413)
    if not allow_request(request, "bank-callback", 120, 60):
        return HttpResponse(status=429)
    try:
        if request.method == "GET":
            data = request.GET
        elif request.content_type == "application/json":
            data = json.loads(request.body)
        else:
            data = request.POST
        provider_id = data.get("mdOrder")
        number = data.get("orderNumber")
        attempts = PaymentAttempt.objects.filter(provider="alfabank")
        if number:
            attempt = attempts.filter(idempotence_key=uuid.UUID(str(number))).first()
            if provider_id:
                safe_provider_id(provider_id)
                if attempt and attempt.provider_id and attempt.provider_id != provider_id:
                    raise InvalidPayment("Номер платежа не совпадает.")
        elif provider_id:
            attempt = attempts.filter(provider_id=safe_provider_id(provider_id)).first()
        else:
            return HttpResponse(status=400)
        if not attempt:
            return HttpResponse(status=404)
        # Query by our stored number/ID. Callback status, amount, operation and
        # checksum cannot change the order or bind an arbitrary bank payment.
        reconcile_attempt(attempt.pk)
    except (ValueError, KeyError, TypeError, AttributeError, InvalidPayment):
        return HttpResponse(status=400)
    except PaymentError:
        return HttpResponse(status=503)
    return HttpResponse(status=200)
