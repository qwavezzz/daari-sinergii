"""Seed customer information without overwriting text already edited by the owner."""

import json
import hashlib
from pathlib import Path
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from apps.content.models import FAQEntry, SiteSettings
from apps.orders.models import StoreSettings, DeliveryMethod


def load_customer_copy():
    data_dir = Path(__file__).resolve().parents[2] / "data"
    return (
        json.loads((data_dir / "customer_pages_20260930.json").read_text(encoding="utf-8")),
        json.loads((data_dir / "customer_pages_previous_hashes.json").read_text(encoding="utf-8")),
    )


def matches_previous_copy(text, known_hashes):
    """Accept all shipped baselines while retaining compatibility with the first hash file."""
    if isinstance(known_hashes, str):
        known_hashes = [known_hashes]
    return hashlib.sha256(text.encode()).hexdigest() in (known_hashes or [])


class Command(BaseCommand):
    help = "Подготовить страницы покупателей и выключенный способ СДЭК с расчётом цены."

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh-defaults",
            action="store_true",
            help="Обновить только неизменённые тексты предыдущей поставки; правки редактора сохранить.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Показать план без записи в БД.")

    @transaction.atomic
    def handle(self, *args, **options):
        data, previous = load_customer_copy()
        dry_run = options["dry_run"]
        refresh = options["refresh_defaults"]
        site = SiteSettings.objects.filter(singleton=1).first() or SiteSettings(singleton=1)
        known = {
            "company_name": "Дары Синергии",
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
            self.stdout.write("Контакты: " + ", ".join(changed))
            if not dry_run:
                site.save(update_fields=changed if site.pk else None)
        store = StoreSettings.objects.filter(pk=1).first() or StoreSettings(pk=1)
        seed_faq = store._state.adding or not any(getattr(store, field).strip() for field in data["pages"])
        changed = []
        for field, value in data["pages"].items():
            current = getattr(store, field)
            if current == value:
                continue
            is_previous = matches_previous_copy(current, previous["pages"].get(field))
            if not current.strip() or (refresh and is_previous):
                setattr(store, field, value)
                changed.append(field)
            elif refresh:
                self.stdout.write(
                    self.style.WARNING(f"Сохранена редакция владельца: {field}; проверьте вручную.")
                )
        if changed:
            self.stdout.write("Страницы: " + ", ".join(changed))
            if not dry_run:
                store.save(update_fields=None if store._state.adding else changed + ["updated_at"])
        # Do not reinsert deleted FAQ entries or reset the owner's ordering on every release.
        if not FAQEntry.objects.exists() and seed_faq:
            self.stdout.write(f"Новый FAQ: {len(data['faq'])} записей.")
            if not dry_run:
                FAQEntry.objects.bulk_create(
                    [FAQEntry(question=q, answer=a, order=i) for i, (q, a) in enumerate(data["faq"])]
                )
        elif refresh:
            answers = dict(data["faq"])
            for entry in FAQEntry.objects.all():
                new_answer = answers.get(entry.question)
                if new_answer is None or entry.answer == new_answer:
                    continue
                if matches_previous_copy(entry.answer, previous["faq"].get(entry.question)):
                    self.stdout.write(f"Обновление FAQ: {entry.pk}.")
                    if not dry_run:
                        entry.answer = new_answer
                        entry.save(update_fields=["answer"])
                else:
                    self.stdout.write(
                        self.style.WARNING(f"Сохранена редакция FAQ: {entry.pk}; проверьте вручную.")
                    )
        if not DeliveryMethod.objects.filter(slug="cdek-pickup").exists():
            self.stdout.write("Новый способ СДЭК: расчёт по ПВЗ, выключен до подключения.")
            if not dry_run:
                DeliveryMethod.objects.create(
                    slug="cdek-pickup",
                    name="СДЭК — пункт выдачи по России",
                    type="cdek_pvz",
                    price=Decimal("0.00"),
                    active=False,
                    address_required=True,
                    is_default=not DeliveryMethod.objects.filter(is_default=True).exists(),
                )
        self.stdout.write(
            self.style.SUCCESS(
                "Предпросмотр завершён, БД не изменена."
                if dry_run
                else "Страницы и FAQ подготовлены. Редакторские тексты, реквизиты и способы доставки сохранены."
            )
        )
        self.stdout.write(
            "Подтвердите продавца, реквизиты, адрес возврата, часы связи и срок подготовки заказа. "
            "Подключите Альфа-Банк, СДЭК и кассу, проверьте упаковки и налоговые настройки. "
            "Приём заказов и платежей не включается этой командой."
        )
