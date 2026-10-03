"""Production defaults. Select config.settings_dev explicitly for local SQLite."""

import os
from pathlib import Path
from urllib.parse import unquote, urlparse
from django.core.exceptions import ImproperlyConfigured
from .local_environment import load_local_environment

load_local_environment()

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = False
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEVELOPMENT = os.environ.get("DJANGO_SETTINGS_MODULE") in {"config.settings_dev", "config.settings_test"}
if not SECRET_KEY:
    if DEVELOPMENT:
        SECRET_KEY = "local-development-only-not-a-production-secret-key"
    else:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY outside the release directory.")
MAIN_HOST = os.environ.get("MAIN_HOST", "dari-sinergii.ru")
SHOP_HOST = os.environ.get("SHOP_HOST", "shop.dari-sinergii.ru")
MAIN_ORIGIN = os.environ.get("MAIN_ORIGIN", f"https://{MAIN_HOST}")
SHOP_ORIGIN = os.environ.get("SHOP_ORIGIN", f"https://{SHOP_HOST}")
SITE_INDEXING_ENABLED = os.environ.get("SITE_INDEXING_ENABLED", "true").lower() == "true"
# Explicit release gate, independent of checkout/payment settings.
SHOP_INDEXING_ENABLED = os.environ.get("SHOP_INDEXING_ENABLED", "false").lower() == "true"
ALLOWED_HOSTS = [MAIN_HOST, "www." + MAIN_HOST, SHOP_HOST]
CSRF_TRUSTED_ORIGINS = [MAIN_ORIGIN, SHOP_ORIGIN]
INSTALLED_APPS = [
    "apps.core.admin_site.BusinessAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core.apps.CoreConfig",
    "apps.content.apps.ContentConfig",
    "apps.reviews.apps.ReviewsConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.cart.apps.CartConfig",
    "apps.orders.apps.OrdersConfig",
    "apps.payments.apps.PaymentsConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.HostRoutingMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.ResponsePolicyMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.public_settings",
                "apps.content.context_processors.site_content",
                "apps.cart.context_processors.cart_summary",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
database_url = urlparse(os.environ.get("DATABASE_URL", ""))
if database_url.scheme in {"postgres", "postgresql"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(database_url.path[1:]),
            "USER": unquote(database_url.username or ""),
            "PASSWORD": unquote(database_url.password or ""),
            "HOST": database_url.hostname or "127.0.0.1",
            "PORT": database_url.port or 5432,
            "CONN_MAX_AGE": 60,
        }
    }
elif DEVELOPMENT:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "var" / "db.sqlite3"}}
else:
    raise ImproperlyConfigured(
        "DATABASE_URL must select PostgreSQL; SQLite is only enabled in explicit dev/test settings."
    )
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation." + name}
    for name in [
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    ]
]
LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Samara"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT", BASE_DIR / "var" / "static"))
STATICFILES_DIRS = [BASE_DIR / "var" / "build" / "static"]
# Vite owns hashed entry filenames; Django copies them without a second hash.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "var" / "media"))
PRIVATE_MEDIA_ROOT = Path(os.environ.get("PRIVATE_MEDIA_ROOT", BASE_DIR / "var" / "private-media"))
CONTENT_VIDEO_PROVIDERS = tuple(filter(None, os.environ.get("CONTENT_VIDEO_PROVIDERS", "").split(",")))
CONTENT_DOCUMENT_MAX_BYTES = int(os.environ.get("CONTENT_DOCUMENT_MAX_BYTES", str(30 * 1024 * 1024)))
CONTENT_IMAGE_MAX_BYTES = int(os.environ.get("CONTENT_IMAGE_MAX_BYTES", str(8 * 1024 * 1024)))
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_NAME = "dari_session"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = int(os.environ.get("CART_SESSION_DAYS", "30")) * 86400
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(os.environ.get("HSTS_SECONDS", "0"))
# Apply HSTS to each served host; include every subdomain only after a separate audit.
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.environ.get("HSTS_INCLUDE_SUBDOMAINS", "false").lower() == "true"
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 32 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
RESERVATION_MINUTES = int(os.environ.get("RESERVATION_MINUTES", "30"))
CHECKOUT_ENABLED = os.environ.get("CHECKOUT_ENABLED", "false").lower() == "true"
PAYMENT_STUB_ENABLED = os.environ.get("PAYMENT_STUB_ENABLED", "false").lower() == "true"
ALFABANK_ENABLED = os.environ.get("ALFABANK_ENABLED", "false").lower() == "true"
ALFABANK_USERNAME = os.environ.get("ALFABANK_USERNAME", "")
ALFABANK_PASSWORD = os.environ.get("ALFABANK_PASSWORD", "")
ALFABANK_TEST_MODE = os.environ.get("ALFABANK_TEST_MODE", "true").lower() == "true"
ALFABANK_LIVE_APPROVED = os.environ.get("ALFABANK_LIVE_APPROVED", "false").lower() == "true"
ALFABANK_RECEIPT_MODE = os.environ.get("ALFABANK_RECEIPT_MODE", "unconfigured")
ALFABANK_TAX_SYSTEM = (
    int(os.environ["ALFABANK_TAX_SYSTEM"]) if os.environ.get("ALFABANK_TAX_SYSTEM") else None
)
CDEK_ENABLED = os.environ.get("CDEK_ENABLED", "false").lower() == "true"
CDEK_TEST_MODE = os.environ.get("CDEK_TEST_MODE", "true").lower() == "true"
CDEK_DEMO_QUOTES_ENABLED = os.environ.get("CDEK_DEMO_QUOTES_ENABLED", "false").lower() == "true"
CDEK_CLIENT_ID = os.environ.get("CDEK_CLIENT_ID", "")
CDEK_CLIENT_SECRET = os.environ.get("CDEK_CLIENT_SECRET", "")
# Use the CDEK directory code for the actual sender city; never infer it from a name.
CDEK_FROM_CITY_CODE = int(os.environ.get("CDEK_FROM_CITY_CODE") or "0")
CDEK_MAP_TILE_URL = os.environ.get("CDEK_MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
CDEK_MAP_ATTRIBUTION = os.environ.get("CDEK_MAP_ATTRIBUTION", "")
CDEK_QUOTE_TTL_SECONDS = int(os.environ.get("CDEK_QUOTE_TTL_SECONDS", "900"))
CDEK_TIMEOUT_SECONDS = int(os.environ.get("CDEK_TIMEOUT_SECONDS", "10"))
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "false").lower() == "true"
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "false" if EMAIL_USE_SSL else "true").lower() == "true"
EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "15"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "")
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO", "")
MANAGER_EMAIL = os.environ.get("MANAGER_EMAIL", "")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
