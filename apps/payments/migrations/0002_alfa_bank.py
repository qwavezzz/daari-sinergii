from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_initial")]

    operations = [
        # Every existing row belongs to the retired integration, regardless of status.
        migrations.AddField(
            model_name="paymentattempt",
            name="provider",
            field=models.CharField(
                "Платёжный сервис",
                max_length=16,
                default="legacy",
                editable=False,
                choices=[("legacy", "Архивный сервис"), ("alfabank", "Альфа-Банк")],
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="paymentattempt",
            name="provider",
            field=models.CharField(
                "Платёжный сервис",
                max_length=16,
                default="alfabank",
                editable=False,
                choices=[("legacy", "Архивный сервис"), ("alfabank", "Альфа-Банк")],
            ),
        ),
        migrations.AddField(
            model_name="paymentattempt",
            name="account_id",
            field=models.CharField("Учётная запись магазина", max_length=100, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="paymentattempt",
            name="test_mode",
            field=models.BooleanField("Тестовая среда", default=True, editable=False),
        ),
    ]
