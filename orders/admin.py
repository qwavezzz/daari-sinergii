from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from .models import DeliveryMethod, Notification, Order, OrderItem, StockReservation, StoreSettings
from payments.models import PaymentAttempt
from .services import transition_order


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return super().has_add_permission(request) and not StoreSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DeliveryMethod)
class DeliveryMethodAdmin(admin.ModelAdmin):
    list_display = ["name", "price", "address_required", "active"]
    list_filter = ["active"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


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
    list_display = [
        "public_id",
        "created_at",
        "name",
        "total",
        "status",
        "financial_status",
        "needs_attention",
    ]
    list_filter = ["status", "financial_status", "needs_attention", "created_at"]
    search_fields = ["public_id", "name", "email", "phone"]
    readonly_fields = [
        field.name for field in Order._meta.fields if field.name not in {"id", "session_key", "checkout_key"}
    ]
    exclude = ["session_key", "checkout_key"]
    inlines = [OrderItemInline, PaymentInline, ReservationInline]
    actions = ["processing", "ready", "completed", "cancel"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def apply_transition(self, request, queryset, target):
        for order in queryset:
            try:
                transition_order(order.pk, target, request.user.pk)
            except ValidationError as exc:
                self.message_user(request, f"{order}: {' '.join(exc.messages)}", messages.ERROR)

    @admin.action(description="Взять в обработку", permissions=["change"])
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
    list_display = ["order", "event", "recipient", "sent_at", "attempts", "last_error"]
    readonly_fields = [field.name for field in Notification._meta.fields]
    list_filter = ["event", "sent_at"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
