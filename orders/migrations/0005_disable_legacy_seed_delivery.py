from decimal import Decimal

from django.db import migrations


def disable_old_seed(apps, schema_editor):
    # Only the exact historical demo preset is converted. Existing order snapshots stay intact.
    apps.get_model("orders", "DeliveryMethod").objects.filter(
        slug="cdek-pickup",
        name="СДЭК — пункт выдачи по России",
        type="static",
        price=Decimal("300.00"),
    ).update(type="cdek_pvz", active=False, price=Decimal("0.00"), address_required=False)


class Migration(migrations.Migration):
    dependencies = [("orders", "0004_deliverymethod_cdek_tariff_code_deliverymethod_type_and_more")]
    operations = [migrations.RunPython(disable_old_seed, migrations.RunPython.noop)]
