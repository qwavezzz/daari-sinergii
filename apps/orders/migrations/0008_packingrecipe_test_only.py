from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0007_packingbox_packingrecipe_packingrecipeitem_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="packingrecipe",
            name="test_only",
            field=models.BooleanField(default=False, verbose_name="Учебная схема — только тестовый СДЭК"),
        ),
    ]
