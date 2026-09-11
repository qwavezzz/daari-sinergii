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
TEMPLATES[0]["APP_DIRS"] = False
TEMPLATES[0]["OPTIONS"]["loaders"] = [
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]
DATABASES["default"]["NAME"].parent.mkdir(parents=True, exist_ok=True) if DATABASES["default"][
    "ENGINE"
].endswith("sqlite3") else None
