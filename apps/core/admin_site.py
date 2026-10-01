from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig
from django.urls import reverse


class BusinessAdminConfig(AdminConfig):
    default_site = "apps.core.admin_site.BusinessAdminSite"


class BusinessAdminSite(AdminSite):
    index_template = "admin/business_index.html"

    def get_app_list(self, request, app_label=None):
        apps = super().get_app_list(request, app_label)
        order = ["orders", "catalog", "content", "reviews", "auth", "payments", "core"]
        names = {"orders": "Заказы и настройки магазина", "catalog": "Товары и категории"}
        for app in apps:
            app["name"] = names.get(app["app_label"], app["name"])
            if app["app_label"] == "orders":
                priority = {"Order": 0, "StoreSettings": 1, "DeliveryMethod": 2, "Notification": 3}
                app["models"].sort(key=lambda model: priority.get(model["object_name"], 9))
            app["single"] = [dict(app)]
        return sorted(
            apps, key=lambda app: order.index(app["app_label"]) if app["app_label"] in order else 99
        )

    def index(self, request, extra_context=None):
        from django.conf import settings
        from apps.orders.models import Notification, Order, StoreSettings
        from apps.orders.notifications import smtp_configuration_error

        context = dict(extra_context or {})
        tasks = []
        if request.user.has_perm("orders.view_order"):
            orders_url = reverse("admin:orders_order_changelist")
            tasks = [
                {
                    "label": "Ожидают сборки",
                    "url": orders_url
                    + "?financial_status__exact=paid&status__exact=new&needs_attention__exact=0",
                    "count": Order.objects.filter(
                        financial_status="paid", status="new", needs_attention=False
                    ).count(),
                },
                {
                    "label": "Собираются",
                    "url": orders_url + "?status__exact=processing",
                    "count": Order.objects.filter(status="processing").count(),
                },
                {
                    "label": "Требуют проверки",
                    "url": orders_url + "?needs_attention__exact=1",
                    "count": Order.objects.filter(needs_attention=True).count(),
                },
            ]
            context["recent_orders"] = Order.objects.order_by("-created_at")[:8]
        context["order_tasks"] = tasks
        if request.user.has_perm("orders.view_storesettings"):
            store = StoreSettings.objects.filter(pk=1).first()
            context["store_settings_url"] = (
                reverse("admin:orders_storesettings_change", args=[1])
                if store
                else reverse("admin:orders_storesettings_add")
            )
            context["manager_email"] = (store.manager_email if store else "") or settings.MANAGER_EMAIL
            context["mail_configuration"] = (
                smtp_configuration_error() or "SMTP настроен. Доставку проверяйте в журнале писем."
            )
            context["payment_configuration"] = (
                "Тестовая оплата: ключи заданы, требуется проверка подключения."
                if settings.ALFABANK_ENABLED
                and settings.ALFABANK_USERNAME
                and settings.ALFABANK_PASSWORD
                and settings.ALFABANK_TEST_MODE
                else "Рабочая оплата настроена."
                if settings.ALFABANK_ENABLED
                and settings.ALFABANK_USERNAME
                and settings.ALFABANK_PASSWORD
                and settings.ALFABANK_LIVE_APPROVED
                else "Оплата не подключена. Настройку выполняет разработчик."
            )
        if request.user.has_perm("orders.view_notification"):
            context["unsent_count"] = Notification.objects.filter(sent_at__isnull=True).count()
        return super().index(request, context)
