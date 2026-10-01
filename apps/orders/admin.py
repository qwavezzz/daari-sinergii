from django.contrib import admin, messages
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.urls import path, reverse
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from .models import (
    DeliveryMethod,
    Notification,
    NotificationSettings,
    Order,
    OrderItem,
    StockReservation,
    StoreSettings,
)
from apps.payments.models import PaymentAttempt
from .services import TRANSITIONS, transition_order


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    readonly_fields = ("updated_at",)
    fieldsets = [
        (
            "Уведомления о заказах",
            {
                "fields": ["manager_email"],
                "description": "Укажите почту сотрудника, который собирает заказы. Если поле пустое, используется адрес из серверной настройки, если он задан.",
            },
        ),
        (
            "Приём заказов",
            {
                "fields": ["checkout_enabled"],
                "description": "Оформление также должно быть включено разработчиком на сервере.",
            },
        ),
        (
            "Условия для покупателей",
            {
                "fields": [
                    "delivery_text",
                    "terms_text",
                    "privacy_text",
                    "returns_text",
                    "contacts_text",
                    "documents_text",
                    "faq_text",
                    "updated_at",
                ],
                "description": "Здесь публикуются утверждённые бизнесом условия. Изменения видны покупателям после сохранения.",
            },
        ),
    ]

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not StoreSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DeliveryMethod)
class DeliveryMethodAdmin(admin.ModelAdmin):
    list_display = ["name", "type", "cdek_tariff_code", "price", "is_default", "vat_code", "active"]
    list_editable = ["price"]
    list_filter = ["active"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.active and obj.price and obj.vat_code is None:
            self.message_user(
                request,
                "Согласуйте ставку НДС доставки и параметры кассы перед приёмом платежей.",
                messages.WARNING,
            )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ["name", "sku", "unit_price", "quantity", "vat_code", "product"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("orders.view_order")


class ManagerOrderItemInline(OrderItemInline):
    fields = ["name", "sku", "quantity", "unit_price"]
    readonly_fields = fields


class PaymentInline(admin.TabularInline):
    model = PaymentAttempt
    extra = 0
    can_delete = False
    fields = ["provider_id", "amount", "currency", "state", "last_checked_at", "last_error"]
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ReservationInline(admin.TabularInline):
    model = StockReservation
    extra = 0
    can_delete = False
    fields = ["product", "quantity", "state", "expires_at"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("orders.view_order")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    view_on_site = False
    change_form_template = "admin/orders/order/change_form.html"
    list_display = [
        "order_number",
        "created_at",
        "name",
        "total",
        "work_status",
        "financial_status",
        "payment_mode",
        "needs_attention",
        "test_mode",
    ]
    list_filter = ["status", "financial_status", "needs_attention", "test_mode", "created_at"]
    search_fields = ["public_id", "name", "email", "phone"]
    readonly_fields = [
        field.name for field in Order._meta.fields if field.name not in {"id", "session_key", "checkout_key"}
    ]
    exclude = ["session_key", "checkout_key", "paid_attempt_id"]
    fieldsets = [
        (
            "Состояние заказа",
            {
                "fields": [
                    "work_status",
                    "financial_status",
                    "payment_mode",
                    "test_mode",
                    "created_at",
                    "needs_attention",
                    "attention_reason",
                ]
            },
        ),
        (
            "Покупатель и получение",
            {
                "fields": [
                    "name",
                    "phone",
                    "email",
                    "delivery_method",
                    "address",
                    "cdek_pickup",
                    "cdek_tariff",
                    "cdek_waybill",
                    "delivery_snapshot",
                    "comment",
                ]
            },
        ),
        ("Сумма заказа", {"fields": ["subtotal", "delivery_price", "total"]}),
        (
            "Дополнительные сведения",
            {
                "fields": ["public_id", "updated_at", "terms_accepted_at", "terms_snapshot"],
                "classes": ["collapse"],
            },
        ),
    ]
    inlines = [OrderItemInline, PaymentInline, ReservationInline]
    actions = ["processing", "ready", "completed", "cancel"]
    readonly_fields = [
        *readonly_fields,
        "work_status",
        "payment_mode",
        "cdek_pickup",
        "cdek_tariff",
        "cdek_waybill",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("trial_payment")

    @admin.display(description="Режим оплаты")
    def payment_mode(self, obj):
        trial = getattr(obj, "trial_payment", None)
        return f"Пробный заказ: {trial.get_state_display()}" if trial else "Банковская оплата"

    @admin.display(description="Пункт СДЭК")
    def cdek_pickup(self, obj):
        point = obj.delivery_snapshot.get("pickup", {})
        return f"{point.get('code', '')} · {obj.address}" if point else "—"

    @admin.display(description="Тариф СДЭК")
    def cdek_tariff(self, obj):
        return obj.delivery_snapshot.get("tariff_code", "—")

    @admin.display(description="Накладная СДЭК")
    def cdek_waybill(self, obj):
        if getattr(obj, "trial_payment", None):
            return "Пробный заказ — отправка не требуется"
        return "Оформить вручную после подтверждения оплаты" if obj.delivery_type == "cdek_pvz" else "—"

    @admin.display(description="Заказ", ordering="pk")
    def order_number(self, obj):
        return f"№ {obj.pk}"

    @admin.display(description="Что делать", ordering="status")
    def work_status(self, obj):
        if obj.needs_attention:
            return "Требует проверки"
        if obj.status == "new":
            return "Ожидает сборки" if obj.financial_status == "paid" else "Ожидает оплаты"
        if obj.status == "processing":
            return "Собирается"
        return obj.get_status_display()

    def get_inlines(self, request, obj):
        return self.inlines if request.user.is_superuser else [ManagerOrderItemInline]

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (title, {**options, "fields": list(options["fields"])}) for title, options in self.fieldsets
        ]
        if obj and not obj.needs_attention:
            fieldsets[0][1]["fields"] = [
                field
                for field in fieldsets[0][1]["fields"]
                if field not in {"needs_attention", "attention_reason"}
            ]
        return fieldsets

    def get_urls(self):
        return [
            path(
                "<int:object_id>/workflow/",
                self.admin_site.admin_view(self.workflow),
                name="orders_order_workflow",
            )
        ] + super().get_urls()

    @method_decorator(require_POST)
    def workflow(self, request, object_id):
        order = self.get_object(request, str(object_id))
        if not order:
            raise Http404
        if not self.has_change_permission(request, order):
            raise PermissionDenied
        target = request.POST.get("target", "")
        try:
            transition_order(order.pk, target, request.user.pk)
        except ValidationError as exc:
            self.message_user(request, " ".join(exc.messages), messages.ERROR)
        else:
            self.log_change(request, order, "Статус заказа: " + target)
            self.message_user(request, "Состояние заказа обновлено.", messages.SUCCESS)
        return HttpResponseRedirect(reverse("admin:orders_order_change", args=[order.pk]))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        order = self.get_object(request, object_id)
        labels = {
            "processing": "Начать сборку",
            "ready": "Готов к выдаче / передан в доставку",
            "completed": "Завершить заказ",
        }
        transitions = []
        if (
            order
            and self.has_change_permission(request, order)
            and order.financial_status == "paid"
            and not order.needs_attention
        ):
            transitions = [
                {"value": key, "label": label}
                for key, label in labels.items()
                if key in TRANSITIONS.get(order.status, set())
            ]
        return super().change_view(
            request,
            object_id,
            form_url,
            {
                **(extra_context or {}),
                "workflow_actions": transitions,
                "title": f"Заказ № {order.pk}" if order else "Заказ",
                "subtitle": None,
                "show_save": False,
                "show_save_and_continue": False,
                "show_save_and_add_another": False,
            },
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def apply_transition(self, request, queryset, target):
        changed = 0
        for order in queryset:
            try:
                transition_order(order.pk, target, request.user.pk)
                self.log_change(request, order, "Статус заказа: " + target)
                changed += 1
            except ValidationError as exc:
                self.message_user(request, f"{order}: {' '.join(exc.messages)}", messages.ERROR)
        if changed:
            self.message_user(request, f"Обновлено заказов: {changed}.", messages.SUCCESS)

    @admin.action(description="Начать сборку выбранных заказов", permissions=["change"])
    def processing(self, request, queryset):
        self.apply_transition(request, queryset, "processing")

    @admin.action(description="Передать в доставку / подготовить к выдаче", permissions=["change"])
    def ready(self, request, queryset):
        self.apply_transition(request, queryset, "ready")

    @admin.action(description="Завершить заказ", permissions=["change"])
    def completed(self, request, queryset):
        self.apply_transition(request, queryset, "completed")

    @admin.action(description="Отменить заказ после проверки оплаты", permissions=["change"])
    def cancel(self, request, queryset):
        self.apply_transition(request, queryset, "canceled")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["order", "event_label", "audience", "recipient", "delivery_status", "sent_at", "attempts"]
    readonly_fields = [field.name for field in Notification._meta.fields]
    list_filter = ["audience", "event", "sent_at"]
    search_fields = ["recipient", "order__public_id"]

    @admin.display(description="Событие", ordering="event")
    def event_label(self, obj):
        return {
            "created": "Заказ оформлен",
            "paid": "Оплата подтверждена",
            "refunded": "Возврат подтверждён",
        }.get(obj.event, "Обновление возврата")

    @admin.display(description="Отправка")
    def delivery_status(self, obj):
        if obj.sent_at:
            return "Принято почтовым сервером"
        return "Ошибка — будет повторная попытка" if obj.last_error else "Ожидает отправки"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NotificationSettings)
class NotificationSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return super().has_add_permission(request) and not NotificationSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if "manager_email" in form.changed_data:
            Notification.objects.filter(
                audience=Notification.Audience.MANAGER,
                sent_at__isnull=True,
                skipped_at__isnull=True,
            ).update(next_attempt_at=timezone.now())
            self.message_user(
                request, "Неотправленные письма менеджеру будут направлены на актуальный адрес."
            )
