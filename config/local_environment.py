"""Optional private settings for local development; production uses EnvironmentFile."""

import json
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


LOCAL_KEYS = {
    "CHECKOUT_ENABLED",
    "YOOKASSA_ENABLED",
    "YOOKASSA_SHOP_ID",
    "YOOKASSA_SECRET_KEY",
    "YOOKASSA_TEST_MODE",
    "ALFABANK_ENABLED",
    "ALFABANK_USERNAME",
    "ALFABANK_PASSWORD",
    "ALFABANK_TEST_MODE",
    "ALFABANK_LIVE_APPROVED",
    "ALFABANK_RECEIPT_MODE",
    "ALFABANK_TAX_SYSTEM",
    "PAYMENT_STUB_ENABLED",
    "CDEK_ENABLED",
    "CDEK_CLIENT_ID",
    "CDEK_CLIENT_SECRET",
    "CDEK_TEST_MODE",
    "CDEK_PUBLIC_SANDBOX",
    "CDEK_FROM_CITY_CODE",
    "CDEK_YANDEX_API_KEY",  # Accept existing local files; the retired widget key is unused.
    "CDEK_MAP_TILE_URL",
    "CDEK_MAP_ATTRIBUTION",
    "EMAIL_BACKEND",
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_USE_TLS",
    "EMAIL_USE_SSL",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "DEFAULT_FROM_EMAIL",
    "EMAIL_TIMEOUT",
}


def load_local_environment():
    if os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings_dev":
        return
    path = Path(__file__).resolve().parent.parent / "var" / "local-settings.json"
    if not path.is_file():
        return
    try:
        values = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(values, dict) or values.keys() - LOCAL_KEYS:
            raise ValueError
        if any(not isinstance(value, (str, bool, int)) for value in values.values()):
            raise ValueError
    except (OSError, ValueError) as exc:
        raise ImproperlyConfigured(
            "Проверьте формат var/local-settings.json по docs/INTEGRATIONS.md."
        ) from exc
    for key, value in values.items():
        os.environ.setdefault(key, str(value).lower() if isinstance(value, bool) else str(value))
