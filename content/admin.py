from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (
    Collection,
    CollectionAlias,
    CollectionSection,
    Document,
    DocumentAlias,
    Industry,
    PublicationStatus,
    SiteSettings,
    SiteText,
    Video,
)
from .views import serve_private_file
from .widgets import PrivateFileInput


class PublicationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "order", "show_on_home", "published_at")
    list_filter = ("status", "show_on_home")
    readonly_fields = ("updated_at", "updated_by", "preview_link", "media_status")
    actions = ("publish_selected", "archive_selected")
    formfield_overrides = {
        models.FileField: {"widget": PrivateFileInput},
        models.ImageField: {"widget": PrivateFileInput},
    }

    def has_publish_permission(self, request):
        return request.user.has_perm(f"{self.opts.app_label}.publish_{self.opts.model_name}")

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if not self.has_publish_permission(request):
            fields.extend(("status", "published_at"))
        return fields

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        if not self.has_change_permission(request, obj):
            private_fields = {
                field.name for field in self.model._meta.fields if isinstance(field, models.FileField)
            }
            fields = [field for field in fields if field not in private_fields]
        return fields

    @admin.display(description="Загруженный файл")
    def media_status(self, obj):
        if obj and (getattr(obj, "file", None) or getattr(obj, "photo", None) or getattr(obj, "cover", None)):
            return "Файл загружен. Используйте закрытый предпросмотр."
        return "Файл не загружен."

    @admin.display(description="Предпросмотр")
    def preview_link(self, obj):
        if not obj or not obj.pk:
            return "Сначала сохраните черновик."
        url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_preview", args=(obj.pk,))
        return format_html('<a href="{}" target="_blank">Открыть закрытый предпросмотр</a>', url)

    def get_urls(self):
        prefix = f"{self.opts.app_label}_{self.opts.model_name}"
        return [
            path(
                "<int:object_id>/preview/", self.admin_site.admin_view(self.preview), name=f"{prefix}_preview"
            ),
            path(
                "<int:object_id>/preview/file/",
                self.admin_site.admin_view(self.preview_file),
                name=f"{prefix}_preview_file",
            ),
        ] + super().get_urls()

    def _preview_object(self, request, object_id):
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404
        if not self.has_view_or_change_permission(request, obj):
            raise PermissionDenied
        return obj

    def preview(self, request, object_id):
        obj = self._preview_object(request, object_id)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Предпросмотр: {obj}",
            "object": obj,
            "opts": self.opts,
            "preview_file_url": reverse(
                f"admin:{self.opts.app_label}_{self.opts.model_name}_preview_file", args=(obj.pk,)
            ),
        }
        response = TemplateResponse(request, "site/materials_preview.html", context)
        response["Cache-Control"] = "private, no-store"
        return response

    def preview_file(self, request, object_id):
        obj = self._preview_object(request, object_id)
        file = getattr(obj, "file", None) or getattr(obj, "photo", None) or getattr(obj, "cover", None)
        if not file:
            raise Http404
        return serve_private_file(file)

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def _change_status(self, request, queryset, status):
        for obj in queryset:
            old = obj.status
            obj.status = status
            obj.updated_by = request.user
            try:
                obj.full_clean()
            except ValidationError as exc:
                self.message_user(request, f"{obj}: {'; '.join(exc.messages)}", messages.ERROR)
                continue
            obj.save()
            self.log_change(request, obj, f"Публикация: {old} → {status}")

    @admin.action(description="Опубликовать выбранные записи", permissions=["publish"])
    def publish_selected(self, request, queryset):
        self._change_status(request, queryset, PublicationStatus.PUBLISHED)

    @admin.action(description="Отправить выбранные записи в архив", permissions=["publish"])
    def archive_selected(self, request, queryset):
        self._change_status(request, queryset, PublicationStatus.ARCHIVED)


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SiteText)
class SiteTextAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "updated_at")
    search_fields = ("key", "label", "value")
    readonly_fields = ("key", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CollectionSectionInline(admin.StackedInline):
    model = CollectionSection
    extra = 0


@admin.register(Collection)
class CollectionAdmin(PublicationAdmin):
    search_fields = ("title", "intro", "slug")
    prepopulated_fields = {"slug": ("title",)}
    inlines = (CollectionSectionInline,)

    def save_model(self, request, obj, form, change):
        if change:
            old = Collection.objects.get(pk=obj.pk)
            if old.slug != obj.slug:
                CollectionAlias.objects.get_or_create(slug=old.slug, defaults={"collection": obj})
        super().save_model(request, obj, form, change)


@admin.register(Industry)
class IndustryAdmin(PublicationAdmin):
    search_fields = ("title", "caption")
    readonly_fields = PublicationAdmin.readonly_fields + ("slug", "image_base")


@admin.register(Document)
class DocumentAdmin(PublicationAdmin):
    search_fields = ("title", "description", "registration")
    list_filter = PublicationAdmin.list_filter + ("is_declaration", "material_type", "collections")
    filter_horizontal = ("collections", "industries", "products")
    prepopulated_fields = {"slug": ("title",)}

    def save_model(self, request, obj, form, change):
        if change:
            old = Document.objects.get(pk=obj.pk)
            if old.slug != obj.slug:
                DocumentAlias.objects.get_or_create(path=f"slug:{old.slug}", defaults={"document": obj})
        super().save_model(request, obj, form, change)


@admin.register(Video)
class VideoAdmin(PublicationAdmin):
    search_fields = ("title", "description")
    filter_horizontal = ("industries", "products")
