import hashlib
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import RateLimitBucket


def allow_request(request, action, limit=20, seconds=60):
    # Proxy headers are deliberately ignored: Nginx also applies limits by remote IP.
    identity = (
        request.META.get("REMOTE_ADDR", "")
        if action == "admin-login"
        else request.session.session_key or request.META.get("REMOTE_ADDR", "")
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
