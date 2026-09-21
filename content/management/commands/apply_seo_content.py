"""Apply a reviewed content revision only where the imported baseline is untouched."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from content.models import Collection, CollectionAlias, CollectionSection, Document, Industry, SiteText

DATA = Path(__file__).resolve().parents[2] / "data"


class Command(BaseCommand):
    help = "SEO-редакция 21.09.2026: по умолчанию просмотр; --apply сохраняет только безопасные изменения."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="Применить редакцию, сохранив правки клиента."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        apply = options["apply"]
        revision = json.loads((DATA / "seo_20260921.json").read_text(encoding="utf-8"))
        baseline = json.loads((DATA / "legacy_content.json").read_text(encoding="utf-8"))
        topics = {topic["id"]: topic for topic in baseline["topics"]}
        self.stdout.write("Применение SEO-редакции." if apply else "ПРОСМОТР: база данных не изменяется.")

        def rows(model):
            return model.objects.select_for_update() if apply else model.objects.all()

        def report(action, name):
            self.stdout.write(f"{action}: {name}")

        new = revision["new_collection"]
        water = rows(Collection).filter(source_key=new["source_key"]).first()
        available = bool(water and water.is_published)
        if water:
            report("Уже существует; сохранено", water.slug)
        elif (
            Collection.objects.filter(slug=new["slug"]).exists()
            or CollectionAlias.objects.filter(slug=new["slug"]).exists()
        ):
            report("ПРОПУСК — адрес занят", new["slug"])
        else:
            report("Создать", new["slug"])
            available = True
            if apply:
                water = Collection.objects.create(
                    **{key: value for key, value in new.items() if key != "sections"},
                    order=0,
                    status="published",
                )
                self._sections(water, new["sections"])
                declaration = (
                    Document.objects.published().filter(source_key="ozone-generator-declaration").first()
                )
                if declaration:
                    water.documents.add(declaration)

        # Repoint only unchanged imported scenes. Custom text, links, slugs and drafts survive.
        for original in baseline["contexts"]:
            key = original["id"]
            industry = rows(Industry).filter(source_key=key).first()
            if not industry or not available:
                continue
            if water and industry.collection_id == water.pk:
                continue
            label = (
                "Материалы о лошадях и КРС"
                if key == "agriculture"
                else "Материалы для спортивных клубов"
                if key == "sport"
                else "Материалы по направлению"
            )
            unchanged = (
                industry.updated_by_id is None
                and industry.is_published
                and industry.slug == key
                and industry.title == original["title"]
                and industry.caption == original["caption"]
                and industry.action_label == label
                and industry.collection_id
                and industry.collection.source_key == key
                and industry.collection.slug == key
                and industry.collection.updated_by_id is None
            )
            if not unchanged:
                report("ПРОПУСК — редакторские изменения", f"отрасль {key}")
                continue
            report("Связать с подбором системы для воды", key)
            if apply:
                industry.collection = water
                industry.action_label = "Подбор системы для воды"
                industry.save(update_fields=["collection", "action_label", "updated_at"])

        for key, desired in revision["collections"].items():
            collection = rows(Collection).filter(source_key=key).first()
            if not collection:
                report("ПРОПУСК — нет исходной подборки", key)
                continue
            old = topics[key]
            sections = list(collection.sections.values_list("title", "body"))
            expected = [tuple(item) for item in old["sections"]]
            already = all(
                getattr(collection, field) == value for field, value in desired.items() if field != "sections"
            )
            if "sections" in desired:
                already = already and sections == [tuple(item) for item in desired["sections"]]
            if already:
                continue
            unchanged = (
                collection.updated_by_id is None
                and collection.is_published
                and collection.slug == key
                and collection.title == old["title"]
                and collection.intro == old["intro"]
                and sections == expected
            )
            if not unchanged:
                report("ПРОПУСК — редакторские изменения", f"подборка {key}")
                continue
            report("Обновить", key)
            if apply:
                for field, value in desired.items():
                    if field != "sections":
                        setattr(collection, field, value)
                collection.save()
                if "sections" in desired:
                    collection.sections.all().delete()
                    self._sections(collection, desired["sections"])

        old_copy = json.loads((DATA / "materials_copy.json").read_text(encoding="utf-8"))
        for key, value in revision["site_text"].items():
            text = rows(SiteText).filter(key=key).first()
            if not text or text.value not in (old_copy[key], value):
                report("ПРОПУСК — отсутствует или изменено редактором", key)
            elif text.value != value:
                report("Обновить", key)
                if apply:
                    text.value = value
                    text.save(update_fields=["value", "updated_at"])

        self.stdout.write("Готово." if apply else "Для сохранения запустите ту же команду с --apply.")

    @staticmethod
    def _sections(collection, sections):
        CollectionSection.objects.bulk_create(
            [
                CollectionSection(collection=collection, title=title, body=body, order=index)
                for index, (title, body) in enumerate(sections)
            ]
        )
