from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .models import PackingBox, PackingRecipe, PackingRecipeItem


@admin.register(PackingBox)
class PackingBoxAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "code",
        "inner_dimensions",
        "outer_dimensions",
        "tare_weight_g",
        "max_weight_g",
        "active",
    ]
    list_filter = ["active"]
    search_fields = ["name", "code"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = [
        ("Коробка", {"fields": ["name", "code", "active"]}),
        (
            "Внутренние размеры",
            {
                "fields": ["inner_length_mm", "inner_width_mm", "inner_height_mm"],
                "description": "Свободное пространство внутри коробки. Измерьте в миллиметрах по тем же осям, что и внешние размеры.",
            },
        ),
        (
            "Внешние размеры",
            {
                "fields": ["outer_length_mm", "outer_width_mm", "outer_height_mm"],
                "description": "Измерьте собранную закрытую коробку. В схеме упаковки дополнительно указываются фактические размеры готовой посылки.",
            },
        ),
        (
            "Вес и нагрузка",
            {
                "fields": ["tare_weight_g", "max_weight_g"],
                "description": "Вес пустой коробки без наполнителя и предельный общий вес по данным её изготовителя. Наполнитель учитывается отдельно в схеме упаковки.",
            },
        ),
        ("Служебные сведения", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    @admin.display(description="Внутри, мм")
    def inner_dimensions(self, obj):
        return f"{obj.inner_length_mm} × {obj.inner_width_mm} × {obj.inner_height_mm}"

    @admin.display(description="Снаружи, мм")
    def outer_dimensions(self, obj):
        return f"{obj.outer_length_mm} × {obj.outer_width_mm} × {obj.outer_height_mm}"


class PackingRecipeItemInline(admin.TabularInline):
    model = PackingRecipeItem
    extra = 1
    autocomplete_fields = ["product"]
    fields = ["product", "quantity"]


@admin.register(PackingRecipe)
class PackingRecipeAdmin(admin.ModelAdmin):
    list_display = ["name", "box", "measured_weight_g", "measurement_status", "test_only", "active"]
    list_filter = ["active", "test_only", "box"]
    search_fields = ["name", "box__name", "items__product__sku", "items__product__name"]
    autocomplete_fields = ["box"]
    readonly_fields = ["measurement_status", "geometry_check", "measured_at", "created_at", "updated_at"]
    inlines = [PackingRecipeItemInline]
    actions = ["confirm_actual_measurements"]
    fieldsets = [
        (
            "Схема упаковки",
            {
                "fields": ["name", "box", "active", "test_only"],
                "description": "Одна схема описывает точный состав одной коробки. Добавьте товары ниже. Для рабочей доставки используются включённые схемы с подтверждёнными замерами. Учебные схемы с вымышленными параметрами доступны только в тестовом СДЭК и не подтверждают реальные замеры.",
            },
        ),
        (
            "Пробная сборка и замеры",
            {
                "fields": [
                    "packing_weight_g",
                    "measured_weight_g",
                    "outer_length_mm",
                    "outer_width_mm",
                    "outer_height_mm",
                    "instructions",
                    "geometry_check",
                ],
                "description": "Соберите указанный состав, закройте коробку и измерьте полный вес и максимальные внешние размеры. В инструкции укажите положение товаров, слои и защиту. Расчёт объёма служит только проверкой ошибок и не заменяет пробную сборку.",
            },
        ),
        (
            "Подтверждение фактических замеров",
            {
                "fields": ["measurement_status", "measured_at"],
                "description": "Сохраните схему. Затем в списке выделите одну схему и выполните действие «Подтвердить пробную сборку и фактические замеры». Подтверждайте только реально собранную и измеренную посылку. Изменение состава, коробки, веса, размеров или инструкции требует повторного подтверждения.",
            },
        ),
        ("Служебные сведения", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    @admin.display(description="Проверка замеров")
    def measurement_status(self, obj):
        if obj.test_only:
            return "Учебные параметры, не реальные замеры"
        if obj.measurements_valid:
            return "Замеры подтверждены"
        if obj.measurement_signature:
            return "Нужно повторить сборку и замеры"
        return "Замеры не подтверждены"

    @admin.display(description="Проверка габаритов")
    def geometry_check(self, obj):
        notes = obj.geometry_notes()
        return (
            " ".join(notes)
            if notes
            else "Габариты сами по себе не подтверждают вместимость. Проверьте её пробной сборкой."
        )

    @admin.action(description="Подтвердить пробную сборку и фактические замеры", permissions=["change"])
    def confirm_actual_measurements(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request, "Выберите одну схему, для которой вы собрали и измерили посылку.", messages.ERROR
            )
            return
        recipe = queryset.get()
        try:
            recipe.confirm_measurements()
        except ValidationError as exc:
            self.message_user(request, f"{recipe.name}: {' '.join(exc.messages)}", messages.ERROR)
            return
        self.log_change(request, recipe, "Подтверждены пробная сборка и фактические замеры посылки.")
        self.message_user(
            request,
            f"Замеры схемы «{recipe.name}» подтверждены. Для расчёта схема также должна быть включена.",
            messages.SUCCESS,
        )
