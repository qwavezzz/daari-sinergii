from django.utils import timezone

from .models import WorkerHeartbeat


def worker_finished(name, failures=0):
    WorkerHeartbeat.objects.update_or_create(
        name=name, defaults={"finished_at": timezone.now(), "failures": failures}
    )
