from django.db import migrations, models

from apps.orders.migration_compat import RemoveConstraintIfExists, skip_duplicate_notifications


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0002_notifications_and_manager_settings"),
        ("orders", "0002_order_notifications"),
    ]

    operations = [
        RemoveConstraintIfExists(model_name="notification", name="one_order_audience_notification"),
        RemoveConstraintIfExists(model_name="notification", name="one_order_notification"),
        migrations.RunPython(skip_duplicate_notifications, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                fields=["order", "event", "recipient"],
                condition=models.Q(skipped_at__isnull=True),
                name="one_order_notification",
            ),
        ),
    ]
