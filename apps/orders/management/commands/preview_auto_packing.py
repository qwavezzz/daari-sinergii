"""Read-only packing preview; optional real API calculation creates no shipment/order."""

import json
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import Product
from apps.orders.automatic_packing import AutomaticPacking
from apps.orders.cdek import CdekClient, TariffUnavailable, _weight_limits
from apps.orders.packing import _plan


class Command(BaseCommand):
    help = "Показать общие коробки для SKU:количество без заказа. --test-data разрешён только этому предпросмотру."

    def add_arguments(self, parser):
        parser.add_argument("--item", action="append", required=True, help="SKU:количество; можно повторять")
        parser.add_argument("--test-data", action="store_true")
        parser.add_argument(
            "--cdek-pvz", help="Дополнительно запросить цены API для указанного ПВЗ; без накладной"
        )
        parser.add_argument("--tariff", type=int, default=136)

    def handle(self, *args, **options):
        counts = {}
        for value in options["item"]:
            sku, separator, raw = value.rpartition(":")
            if not separator or not sku or not raw.isascii() or not raw.isdigit() or not 1 <= int(raw) <= 100:
                raise CommandError("Use --item SKU:quantity with quantity 1..100")
            counts[sku] = counts.get(sku, 0) + int(raw)
        if sum(counts.values()) > 100:
            raise CommandError("At most 100 units per preview")
        products = list(Product.objects.filter(sku__in=counts).order_by("pk"))
        if len(products) != len(counts):
            raise CommandError("Some product SKUs were not found")
        items = [SimpleNamespace(product=p, quantity=counts[p.sku]) for p in products]
        if any(p.price is None for p in products):
            raise CommandError("Set product prices for declared value")
        declared = sum((p.price * counts[p.sku] for p in products), Decimal("0"))
        try:
            prepared = AutomaticPacking(items, allow_test=options["test_data"])
            client, point, limits = None, None, None
            if options["cdek_pvz"]:
                client = CdekClient()
                point = client.pickup(options["cdek_pvz"])
                sender = client.shipment_point()
                recipient_limits = _weight_limits(point.get("weight_min_g"), point.get("weight_max_g"))
                sender_limits = (
                    _weight_limits(sender.get("weight_min_g"), sender.get("weight_max_g"))
                    if sender
                    else (0, 0)
                )
                maximums = [n for n in (recipient_limits[1], sender_limits[1]) if n]
                limits = (max(recipient_limits[0], sender_limits[0]), min(maximums) if maximums else 0)
            results = []
            for parcels in prepared.options(limits=limits):
                plan = _plan(parcels)
                row = {"packing": plan, "declared_value": str(declared)}
                if client:
                    try:
                        row["quote"] = client.calculate(
                            options["tariff"], point, plan["packages"], declared_value=declared
                        )
                    except TariffUnavailable:
                        continue
                    row["carrier_price"] = row["quote"]["price"]
                    row["packing_price"] = plan["packing_price"]
                    row["total_delivery_price"] = str(
                        Decimal(row["carrier_price"]) + Decimal(row["packing_price"])
                    )
                results.append(row)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from None
        if client:
            if not results:
                raise CommandError("CDEK rejected all checked packing options")
            results.sort(key=lambda r: Decimal(r["total_delivery_price"]))
        self.stdout.write(
            json.dumps(
                {
                    "preview_only": True,
                    "test_data_allowed": options["test_data"],
                    "options": results,
                    "selected_option": 0,
                    "shipment_created": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
