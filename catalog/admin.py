from django import forms
from django.contrib import admin
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from core.models import AuditEntry
from .models import Category, Product, ProductAttribute, ProductImage


class ImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class AttributeInline(admin.TabularInline):
    model = ProductAttribute
    extra = 0


class ProductAdminForm(forms.ModelForm):
    stock_snapshot = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Product
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["stock_snapshot"] = signing.dumps(
                [self.instance.pk, self.instance.stock, self.instance.reserved_stock], salt="admin-stock"
            )

    def clean(self):
        data = super().clean()
        if self.instance.pk:
            current = Product.objects.select_for_update().get(pk=self.instance.pk)
            try:
                snapshot = signing.loads(data.get("stock_snapshot", ""), salt="admin-stock")
            except signing.BadSignature:
                snapshot = None
            if snapshot != [current.pk, current.stock, current.reserved_stock]:
                raise ValidationError(
                    "Остаток или резерв изменился, пока вы редактировали товар. Обновите страницу и повторите изменение."
                )
            self.instance.reserved_stock = current.reserved_stock
        return data


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "active", "sort_order"]
    list_filter = ["active"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = ["name", "sku", "price", "status", "purchasable", "stock", "reserved_stock"]
    list_filter = ["status", "purchasable", "categories"]
    search_fields = ["name", "sku"]
    readonly_fields = ["reserved_stock", "created_at", "updated_at"]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ["categories"]
    inlines = [ImageInline, AttributeInline]

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if change:
                current = Product.objects.select_for_update().get(pk=obj.pk)
                obj.reserved_stock = current.reserved_stock
                if "stock" not in form.changed_data:
                    obj.stock = current.stock
                obj.full_clean()
                scalar = {field.name for field in Product._meta.concrete_fields}
                fields = scalar.intersection(form.changed_data) | {"updated_at"}
                obj.save(update_fields=fields)
            else:
                super().save_model(request, obj, form, change)
        if {"price", "status", "stock"}.intersection(form.changed_data):
            AuditEntry.objects.create(
                kind="catalog.updated",
                object_id=str(obj.pk),
                message=f"Поля: {', '.join(form.changed_data)}; сотрудник {request.user.pk}",
            )
