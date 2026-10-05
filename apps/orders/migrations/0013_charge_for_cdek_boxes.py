from django.db import migrations, models
from django.utils import timezone


def set_cdek_charging(apps, schema_editor):
    # Apply the owner's choice to previously unconfigured CDEK profiles.
    # Keep recorded prices, explicit existing policies and historical orders.
    boxes = apps.get_model("orders", "PackingBox")
    boxes.objects.using(schema_editor.connection.alias).filter(
        supplier="cdek", auto_test_only=False, auto_price_mode=""
    ).update(
        auto_price_mode="charge",
        auto_measurement_signature="",
        auto_measured_at=None,
        updated_at=timezone.now(),
    )


class Migration(migrations.Migration):
    dependencies = [("orders", "0012_packingbox_auto_price_packingbox_auto_price_mode")]

    operations = [
        migrations.AlterField(
            model_name="packingbox",
            name="auto_price_mode",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Выберите способ учёта"),
                    ("included", "Учтена в цене товара"),
                    ("charge", "Добавлять к доставке"),
                ],
                default="charge",
                max_length=12,
                verbose_name="Как учитывать стоимость упаковки",
            ),
        ),
        migrations.RunPython(set_cdek_charging, migrations.RunPython.noop),
    ]
