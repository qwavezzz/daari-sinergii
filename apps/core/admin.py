from django.contrib import admin
from .models import AuditEntry, StoreAcceptance


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


@admin.register(StoreAcceptance)
class StoreAcceptanceAdmin(admin.ModelAdmin):
    list_display = ["kind", "confirmed_at", "reference"]
    readonly_fields = ["confirmed_at"]
    fields = ["kind", "reference", "confirmed_at"]

    def save_model(self, request, obj, form, change):
        from .acceptance import configuration_digest

        obj.configuration_digest = configuration_digest(obj.kind)
        super().save_model(request, obj, form, change)
        AuditEntry.objects.create(
            kind="store.acceptance",
            object_id=obj.kind,
            message=f"Приёмку записал сотрудник {request.user.pk}.",
        )
