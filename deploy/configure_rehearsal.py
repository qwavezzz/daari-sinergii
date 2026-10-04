"""Explicit hosted demo setup; no debug mode, bank operations or real product edits."""

import argparse
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


def environment_text(original, public_id, public_secret):
    values = {
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "CHECKOUT_ENABLED": "true",
        "PAYMENT_STUB_ENABLED": "true",
        "ALFABANK_ENABLED": "false",
        "ALFABANK_TEST_MODE": "true",
        "ALFABANK_LIVE_APPROVED": "false",
        "CDEK_ENABLED": "true",
        "CDEK_TEST_MODE": "true",
        "CDEK_CLIENT_ID": public_id,
        "CDEK_CLIENT_SECRET": public_secret,
        "CDEK_FROM_CITY_CODE": "431",
        "SHOP_INDEXING_ENABLED": "false",
    }
    # Credentials are the public sandbox pair shipped with the application.
    # Reject unexpected contents rather than interpreting shell or systemd syntax.
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in values.values()):
        raise ValueError("Unexpected rehearsal setting format")
    kept = []
    for line in original.splitlines(keepends=True):
        match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match and match[1] in values:
            if line.rstrip().endswith("\\"):
                raise ValueError("Multiline target setting: edit EnvironmentFile manually")
            continue
        kept.append(line)
    return "".join(kept).rstrip("\n") + "\n" + "".join(f"{key}={value}\n" for key, value in values.items())


def update_environment(path, public_id, public_secret):
    if path.is_symlink():
        raise ValueError("EnvironmentFile must be a regular file")
    metadata = path.stat()
    text = environment_text(path.read_text(encoding="utf-8"), public_id, public_secret)
    descriptor, temporary = tempfile.mkstemp(prefix=".rehearsal-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.chown(temporary, metadata.st_uid, metadata.st_gid)
        os.chmod(temporary, stat.S_IMODE(metadata.st_mode))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_database():
    from django.conf import settings
    from django.core.exceptions import ValidationError
    from apps.catalog.models import Product
    from apps.payments.models import PaymentAttempt

    if (
        settings.DEBUG
        or settings.DEVELOPMENT
        or not settings.SESSION_COOKIE_SECURE
        or not settings.CSRF_COOKIE_SECURE
        or not settings.CHECKOUT_ENABLED
        or not settings.PAYMENT_STUB_ENABLED
        or settings.ALFABANK_ENABLED
        or not settings.ALFABANK_TEST_MODE
        or settings.ALFABANK_LIVE_APPROVED
        or not settings.CDEK_ENABLED
        or not settings.CDEK_TEST_MODE
    ):
        raise ValidationError("Hosted rehearsal requires secure production settings and trial-only payments")
    published = Product.objects.filter(status="published", purchasable=True)
    if not published.exists() or published.exclude(sku__startswith="DEMO-").exists():
        raise ValidationError("Only an existing DEMO-only catalog can be enabled by this installer")
    if PaymentAttempt.objects.exists():
        raise ValidationError("Bank payment history exists; configure a separate rehearsal environment")


def configure_database():
    from django.core.management import call_command
    from django.db import transaction
    from apps.catalog.models import Product
    from apps.orders.models import DeliveryMethod, StoreSettings

    with transaction.atomic():
        validate_database()
        call_command("setup_customer_pages", refresh_defaults=True)
        method, _ = DeliveryMethod.objects.get_or_create(
            slug="cdek-vps-rehearsal",
            defaults={
                "name": "СДЭК — пункт выдачи",
                "type": "cdek_pvz",
                "price": 0,
                "cdek_tariff_code": 136,
                "address_required": False,
            },
        )
        if method.type != "cdek_pvz" or method.cdek_tariff_code != 136:
            raise ValueError("Existing rehearsal delivery has unexpected settings")
        DeliveryMethod.objects.exclude(pk=method.pk).update(active=False, is_default=False)
        method.active = method.is_default = True
        method.save(update_fields=["active", "is_default"])
        dimensions = {
            "package_weight_g": 400,
            "package_length_cm": 20,
            "package_width_cm": 10,
            "package_height_cm": 10,
        }
        count = 0
        for product in Product.objects.filter(sku__startswith="DEMO-"):
            missing = [field for field in dimensions if not getattr(product, field)]
            if missing:
                for field in missing:
                    setattr(product, field, dimensions[field])
                product.save(update_fields=[*missing, "updated_at"])
                count += 1
        store = StoreSettings.objects.get(pk=1)
        store.checkout_enabled = True
        store.save(update_fields=["checkout_enabled", "updated_at"])
    print(f"Rehearsal ready; demo packages filled: {count}. No bank payments, waybills or emails sent.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["environment", "check", "database"])
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--environment", type=Path, default=Path("/etc/dari/dari.env"))
    args = parser.parse_args()
    sys.path.insert(0, str(args.release.resolve()))
    if args.action == "environment":
        from config.cdek_sandbox import PUBLIC_CLIENT_ID, PUBLIC_CLIENT_SECRET

        update_environment(args.environment, PUBLIC_CLIENT_ID, PUBLIC_CLIENT_SECRET)
        print("Rehearsal flags set; private settings preserved; credentials omitted.")
        return
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django

    django.setup()
    if args.action == "check":
        validate_database()
    else:
        configure_database()


if __name__ == "__main__":
    main()
