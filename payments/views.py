import json
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import PaymentAttempt
from .provider import InvalidPayment, PaymentError, YooKassaClient, safe_provider_id
from .services import apply_payment, apply_refund


@csrf_exempt
@require_POST
def webhook(request):
    if len(request.body) > 65536:
        return HttpResponse(status=413)
    try:
        data = json.loads(request.body)
        event = data["event"]
        provider_id = safe_provider_id(data["object"]["id"])
        if data.get("type") != "notification" or event not in {
            "payment.succeeded",
            "payment.canceled",
            "payment.waiting_for_capture",
            "refund.succeeded",
        }:
            return HttpResponse(status=400)
        client = YooKassaClient()
        if event.startswith("payment."):
            # The body is an untrusted notification hint. Only authenticated GET data is authoritative.
            verified = client.get_payment(provider_id)
            attempt = PaymentAttempt.objects.filter(provider_id=provider_id).first()
            if not attempt:
                # A webhook can beat the response to our create request. Bind only after verification.
                attempt = PaymentAttempt.objects.filter(
                    order__public_id=verified.order_id,
                    provider_id__isnull=True,
                    state__in=["creating", "unknown"],
                ).first()
            if not attempt:
                return HttpResponse(status=404)
            apply_payment(attempt.pk, verified)
        else:
            refund = client.get_refund(provider_id)
            attempt = PaymentAttempt.objects.filter(provider_id=refund.get("payment_id")).first()
            if not attempt:
                return HttpResponse(status=404)
            verified = client.get_payment(attempt.provider_id)
            apply_payment(attempt.pk, verified)
            if refund.get("id") != provider_id:
                raise InvalidPayment("Неожиданный возврат.")
            apply_refund(attempt.pk, refund)
    except (ValueError, KeyError, TypeError, InvalidPayment):
        return HttpResponse(status=400)
    except PaymentError:
        return HttpResponse(status=503)
    return HttpResponse(status=200)
