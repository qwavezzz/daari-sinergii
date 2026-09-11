from django.contrib import admin
from .models import AuditEntry


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = ["created_at", "kind", "object_id", "message"]
    list_filter = ["kind", "created_at"]
    search_fields = ["object_id", "message"]
    readonly_fields = ["created_at", "kind", "object_id", "message"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
