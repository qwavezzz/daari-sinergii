from .settings_dev import *  # noqa: F403

SECRET_KEY = "tests-only-secret-key-for-dari-sinergii"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_FROM_EMAIL = "test@example.test"
MANAGER_EMAIL = "manager@example.test"
CHECKOUT_ENABLED = True
