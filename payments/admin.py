from django.contrib import admin
from .models import PaymentAttempt, PaymentEvent, Refund


class FinancialAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields if field.name not in set(self.exclude or [])]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(FinancialAdmin):
    list_display = ["order", "provider_id", "amount", "state", "last_checked_at", "last_error"]
    list_filter = ["state", "created_at"]
    search_fields = ["provider_id", "order__public_id"]
    exclude = ["request_payload", "confirmation_url"]


@admin.register(Refund)
class RefundAdmin(FinancialAdmin):
    list_display = ["provider_id", "attempt", "amount", "state"]
    list_filter = ["state"]


@admin.register(PaymentEvent)
class PaymentEventAdmin(FinancialAdmin):
    list_display = ["attempt", "event_type", "verified_at"]
