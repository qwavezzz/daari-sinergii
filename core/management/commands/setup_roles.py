from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Создать роли редактора и менеджера с минимальными правами."

    def handle(self, *args, **options):
        editor, _ = Group.objects.get_or_create(name="Контент-редактор")
        editor.permissions.set(
            Permission.objects.filter(content_type__app_label__in=["content", "reviews"]).exclude(
                codename="delete_sitesettings"
            )
        )
        manager, _ = Group.objects.get_or_create(name="Менеджер магазина")
        permissions = (
            Permission.objects.filter(content_type__app_label="catalog")
            | Permission.objects.filter(
                content_type__app_label="orders",
                content_type__model__in=["order", "notification"],
                codename__startswith="view_",
            )
            | Permission.objects.filter(content_type__app_label="orders", codename="change_order")
            | Permission.objects.filter(
                content_type__app_label="orders",
                content_type__model="notificationsettings",
                codename__in=[
                    "view_notificationsettings",
                    "add_notificationsettings",
                    "change_notificationsettings",
                ],
            )
            | Permission.objects.filter(
                content_type__app_label="orders", content_type__model="deliverymethod"
            )
            | Permission.objects.filter(content_type__app_label="payments", codename__startswith="view_")
        )
        manager.permissions.set(permissions.distinct())
        self.stdout.write(
            self.style.SUCCESS("Роли созданы. Пользователям необходимо отдельно назначить is_staff и группу.")
        )
