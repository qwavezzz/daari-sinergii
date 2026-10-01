from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0003_merge_notification_branches"),
        ("orders", "0005_disable_legacy_seed_delivery"),
    ]

    operations = []
