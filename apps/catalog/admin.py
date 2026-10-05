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
    confirm_auto_measurements = forms.BooleanField(
        label="Я измерил(а) товар с защитой и проверил(а) допустимое положение и нагрузку",
        required=False,
        help_text="Подтверждает параметры для автоматической укладки. Учебные данные подтверждать нельзя.",
    )

    class Meta:
        model = Product
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["unit_stack_limit_g"].required = False
        self.fields["unit_packing_group"].required = False
        if self.instance.pk:
            self.initial["stock_snapshot"] = signing.dumps(
                [self.instance.pk, self.instance.stock, self.instance.reserved_stock], salt="admin-stock"
            )

    def clean(self):
        data = super().clean()
        if data.get("unit_stack_limit_g") is None:
            data["unit_stack_limit_g"] = 0
        if not data.get("unit_packing_group") and data.get("shipping_mode") != "automatic":
            data["unit_packing_group"] = self.instance.unit_packing_group or "general"
        if data.get("confirm_auto_measurements"):
            from apps.orders.auto_profiles import UNIT_FIELDS, validate

            candidate = Product(**{field: data.get(field) for field in UNIT_FIELDS})
            try:
                if candidate.unit_test_only:
                    raise ValidationError("Учебные параметры нельзя подтвердить как реальные замеры.")
                validate(candidate, "unit")
            except ValidationError as exc:
                self.add_error("confirm_auto_measurements", exc)
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
        "auto_measurement_status",
        "unit_measured_at",
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
                "description": "Автоматический подбор объединяет совместимые товары по размерам. Проверенные схемы подходят для особой укладки. Отдельная посылка всегда отправляется отдельно.",
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
            "Автоматический подбор коробки",
            {
                "fields": [
                    "unit_allow_rotation",
                    "unit_stack_limit_g",
                    "unit_packing_group",
                    "unit_test_only",
                    "confirm_auto_measurements",
                    "auto_measurement_status",
                    "unit_measured_at",
                ],
                "description": "Используются размеры товара с индивидуальной защитой из раздела выше. По умолчанию товар остаётся вертикальным, сверху ничего не ставится. Одинаковая группа разрешает общую коробку.",
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

    @admin.display(description="Параметры автоподбора")
    def auto_measurement_status(self, obj):
        if obj.unit_test_only:
            return "Учебные данные: рабочее оформление не разрешено."
        return (
            "Подтверждены и актуальны."
            if obj.auto_measurements_valid
            else "Нужны замеры и подтверждение текущих параметров."
        )

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
            if form.cleaned_data.get("confirm_auto_measurements") is True:
                obj.confirm_auto_measurements()
                self.log_change(request, obj, "Подтверждены параметры защищённого товара для автоподбора.")
        if {"price", "status", "stock"}.intersection(form.changed_data):
            AuditEntry.objects.create(
                kind="catalog.updated",
                object_id=str(obj.pk),
                message=f"Поля: {', '.join(form.changed_data)}; сотрудник {request.user.pk}",
            )
