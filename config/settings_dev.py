from .settings import *  # noqa: F403

DEBUG = True
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
MAIN_HOST = "localhost"
SHOP_HOST = "shop.localhost"
MAIN_ORIGIN = os.environ.get("MAIN_ORIGIN", "http://localhost:8000")
SHOP_ORIGIN = os.environ.get("SHOP_ORIGIN", "http://shop.localhost:8000")
ALLOWED_HOSTS = [MAIN_HOST, SHOP_HOST, "127.0.0.1", "[::1]", "testserver"]
CSRF_TRUSTED_ORIGINS = [MAIN_ORIGIN, SHOP_ORIGIN, "http://127.0.0.1:8000"]
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# Local rehearsal: real CDEK sandbox requests, simulated payment, no bank charge.
CHECKOUT_ENABLED = os.environ.get("CHECKOUT_ENABLED", "true").lower() == "true"
PAYMENT_STUB_ENABLED = os.environ.get("PAYMENT_STUB_ENABLED", "true").lower() == "true"
CDEK_ENABLED = os.environ.get("CDEK_ENABLED", "true").lower() == "true"
CDEK_FROM_CITY_CODE = int(os.environ.get("CDEK_FROM_CITY_CODE") or "431")
if (
    CDEK_TEST_MODE
    and not CDEK_CLIENT_ID
    and not CDEK_CLIENT_SECRET
    and os.environ.get("CDEK_PUBLIC_SANDBOX", "true").lower() == "true"
):
    from .cdek_sandbox import PUBLIC_CLIENT_ID, PUBLIC_CLIENT_SECRET

    CDEK_CLIENT_ID = PUBLIC_CLIENT_ID
    CDEK_CLIENT_SECRET = PUBLIC_CLIENT_SECRET
TEMPLATES[0]["APP_DIRS"] = False
TEMPLATES[0]["OPTIONS"]["loaders"] = [
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]
DATABASES["default"]["NAME"].parent.mkdir(parents=True, exist_ok=True) if DATABASES["default"][
    "ENGINE"
].endswith("sqlite3") else None
