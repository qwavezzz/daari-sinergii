from django.apps import AppConfig
import os
import sys


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
    verbose_name = "Система"

    def ready(self):
        if (
            os.environ.get("DJANGO_SETTINGS_MODULE") == "config.settings_dev"
            and len(sys.argv) > 1
            and sys.argv[1] == "runserver"
            and (os.environ.get("RUN_MAIN") == "true" or "--noreload" in sys.argv)
        ):
            from .dev_workers import start_local_worker

            start_local_worker()
