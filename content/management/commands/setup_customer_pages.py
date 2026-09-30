"""Seed customer information without overwriting text already edited by the owner."""

import json
from pathlib import Path
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from content.models import FAQEntry, SiteSettings
from orders.models import StoreSettings, DeliveryMethod


class Command(BaseCommand):
    help = "Заполнить пустые страницы покупателей, добавить FAQ и доставку СДЭК за 300 ₽."

    @transaction.atomic
    def handle(self, *args, **options):
        data = json.loads(
            (Path(__file__).resolve().parents[2] / "data" / "customer_pages_20260930.json").read_text(
                encoding="utf-8"
            )
        )
        site, _ = SiteSettings.objects.get_or_create(singleton=1)
        known = {
            "company_name": "Дары Синергии",
            "legal_name": "ИП Бобко Роман Викторович",
            "email": "sintez2016@gmail.com",
            "phone": "+79060104066",
            "phone_label": "+7 (906) 010-40-66",
        }
        changed = []
        for field, value in known.items():
            if not getattr(site, field).strip():
                setattr(site, field, value)
                changed.append(field)
        if changed:
            site.save(update_fields=changed)
        store, _ = StoreSettings.objects.get_or_create(pk=1)
        changed = []
        for field, value in data["pages"].items():
            if not getattr(store, field).strip():
                setattr(store, field, value)
                changed.append(field)
        if changed:
            store.save(update_fields=changed + ["updated_at"])
        # Do not reinsert deleted FAQ entries or reset the owner's ordering on every release.
        if not FAQEntry.objects.exists():
            FAQEntry.objects.bulk_create(
                [FAQEntry(question=q, answer=a, order=i) for i, (q, a) in enumerate(data["faq"])]
            )
        method, _ = DeliveryMethod.objects.get_or_create(
            slug="cdek-pickup",
            defaults={
                "name": "СДЭК — пункт выдачи по России",
                "price": Decimal("300.00"),
                "active": True,
                "address_required": True,
                "is_default": not DeliveryMethod.objects.filter(is_default=True).exists(),
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Страницы, FAQ и доставка подготовлены. Существующие тексты и тарифы сохранены."
            )
        )
        self.stdout.write(
            "Заполните ИНН, ОГРНИП, адреса и часы связи; согласуйте срок подготовки заказа. "
            "Для чеков укажите ставку НДС доставки. Приём заказов и платежей не включается этой командой."
        )
