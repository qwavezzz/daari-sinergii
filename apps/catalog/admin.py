from django import forms
from django.contrib import admin
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from apps.core.models import AuditEntry
from .models import Category, Product, ProductAttribute, ProductImage


class ImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class AttributeInline(admin.TabularInline):
    model = ProductAttribute
    extra = 0


class ProductAdminForm(forms.ModelForm):
    stock_snapshot = forms.CharField(widget=forms.HiddenInput, required=False)
    confirm_package_measurements = forms.BooleanField(
        label="Я собрал(а) отдельную посылку и проверил(а) её вес и внешние размеры",
        required=False,
        help_text="Отметьте только после реального замера. Сохранение без отметки не подтверждает новые значения.",
    )

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
        if data.get("confirm_package_measurements"):
            candidate = Product(
                **{
                    field: data.get(field)
                    for field in (
                        "shipping_mode",
                        "package_weight_g",
                        "package_length_cm",
                        "package_width_cm",
                        "package_height_cm",
                    )
                }
            )
            try:
                candidate.validate_package_measurements()
            except ValidationError as exc:
                for field, errors in exc.message_dict.items():
                    self.add_error(field, errors)
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
    list_display = [
        "name",
        "sku",
        "price",
        "status",
        "purchasable",
        "stock",
        "reserved_stock",
        "shipping_mode",
    ]
    list_filter = ["status", "purchasable", "categories", "shipping_mode"]
    search_fields = ["name", "sku"]
    readonly_fields = [
        "reserved_stock",
        "created_at",
        "updated_at",
        "package_measurement_status",
        "package_measured_at",
    ]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ["categories"]
    inlines = [ImageInline, AttributeInline]
    fieldsets = [
        ("Карточка товара", {"fields": ["name", "categories", "short_description", "description"]}),
        (
            "Цена и наличие",
            {
                "fields": ["price", "stock", "reserved_stock", "stock_snapshot"],
                "description": "Укажите общее количество на складе. Резерв рассчитывается автоматически для оформленных заказов.",
            },
        ),
        (
            "Показ на сайте",
            {
                "fields": ["status", "purchasable", "sort_order"],
                "description": "Чтобы товар можно было купить, опубликуйте его, разрешите покупку и укажите цену и остаток.",
            },
        ),
        (
            "Упаковка для доставки",
            {
                "fields": ["shipping_mode"],
                "description": "Для нескольких товаров в одной коробке выберите общую упаковку и добавьте проверенные схемы в разделе «Схемы упаковки».",
            },
        ),
        (
            "Товар для общей коробки",
            {
                "fields": ["unit_weight_g", "unit_length_mm", "unit_width_mm", "unit_height_mm"],
                "description": "Измерьте товар с индивидуальной защитой, без общей транспортной коробки. Вес — в граммах, размеры — в миллиметрах. Для каждого объёма или варианта заведите отдельный товар.",
            },
        ),
        (
            "Отдельная посылка на одну единицу",
            {
                "fields": [
                    "package_weight_g",
                    "package_length_cm",
                    "package_width_cm",
                    "package_height_cm",
                    "confirm_package_measurements",
                    "package_measurement_status",
                    "package_measured_at",
                ],
                "description": "Для отправки каждой единицы отдельной посылкой: полный вес вместе с коробкой и наполнителем в граммах; внешние размеры закрытой посылки в сантиметрах, с округлением вверх. После изменения повторите замер и подтвердите его отметкой ниже.",
            },
        ),
        (
            "Артикул и адрес страницы",
            {
                "fields": ["sku", "slug"],
                "description": "Артикул — ваш внутренний код товара. Адрес страницы заполняется из названия; сохраняйте его после публикации.",
            },
        ),
        (
            "Налоговые и служебные сведения",
            {
                "fields": ["vat_code", "created_at", "updated_at"],
                "classes": ["collapse"],
                "description": "Ставку для чеков указывает ответственный за налоги. Перед реальными продажами её нужно проверить.",
            },
        ),
    ]

    @admin.display(description="Проверка замеров отдельной посылки")
    def package_measurement_status(self, obj):
        if obj.shipping_mode == Product.ShippingMode.COMBINED:
            return "Общая коробка: состав и замеры подтверждаются в схеме упаковки."
        if obj.package_measurements_valid:
            return "Замеры подтверждены и соответствуют текущим значениям."
        if obj.package_measurement_signature:
            return "Параметры изменились. Повторите замер и подтвердите новые значения."
        return "Замеры не подтверждены. До реального замера точный расчёт доставки недоступен."

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
            if form.cleaned_data.get("confirm_package_measurements") is True:
                obj.confirm_package_measurements()
                self.log_change(request, obj, "Подтверждены фактические замеры отдельной посылки.")
        if {"price", "status", "stock"}.intersection(form.changed_data):
            AuditEntry.objects.create(
                kind="catalog.updated",
                object_id=str(obj.pk),
                message=f"Поля: {', '.join(form.changed_data)}; сотрудник {request.user.pk}",
            )
