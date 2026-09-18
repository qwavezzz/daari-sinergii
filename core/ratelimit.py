import hashlib
from ipaddress import ip_address
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import RateLimitBucket


def client_address(request):
    remote = request.META.get("REMOTE_ADDR", "")
    # Gunicorn has an empty REMOTE_ADDR on the private Unix socket. Only then
    # trust X-Real-IP, which our Nginx snippet overwrites (never appends).
    # A TCP client cannot choose its identity using a forwarded header.
    if not remote:
        try:
            return str(ip_address(request.META.get("HTTP_X_REAL_IP", "")))
        except ValueError:
            pass
    return remote


def allow_request(request, action, limit=20, seconds=60):
    identity = (
        client_address(request)
        if action == "admin-login"
        else request.session.session_key or client_address(request)
    )
    key = hashlib.sha256(f"{action}:{identity}".encode()).hexdigest()
    with transaction.atomic():
        bucket, _ = RateLimitBucket.objects.get_or_create(key=key, defaults={"window_start": timezone.now()})
        bucket = RateLimitBucket.objects.select_for_update().get(pk=bucket.pk)
        if bucket.window_start < timezone.now() - timedelta(seconds=seconds):
            bucket.window_start, bucket.count = timezone.now(), 0
        bucket.count += 1
        bucket.save(update_fields=["count", "window_start"])
        return bucket.count <= limit
