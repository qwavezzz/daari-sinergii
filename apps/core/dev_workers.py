"""Convenient local retries; production runs the supplied systemd timers."""

import logging
import time
from io import StringIO
from threading import Thread

from django.conf import settings
from django.core.management import call_command
from django.db import close_old_connections


def start_local_worker():
    Thread(target=_work, name="local-shop-notifications", daemon=True).start()


def _work():
    from apps.orders.notifications import smtp_configuration_error

    logger = logging.getLogger(__name__)
    while True:
        time.sleep(15)
        try:
            close_old_connections()
            if settings.YOOKASSA_ENABLED and settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY:
                call_command("reconcile_payments", limit=10, stdout=StringIO())
            if not smtp_configuration_error():
                call_command("send_notifications", limit=10, stdout=StringIO())
        except Exception as exc:
            logger.warning("Локальная фоновая проверка отложена (%s).", type(exc).__name__)
        finally:
            close_old_connections()
