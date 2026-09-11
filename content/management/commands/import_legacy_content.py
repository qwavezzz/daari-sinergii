"""Import the reviewed baseline once; repeated deployment never replaces editor changes."""

import json
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from content.models import (
    Collection,
    CollectionSection,
    Document,
    DocumentAlias,
    Industry,
    PublicationStatus,
    SiteSettings,
    SiteText,
)
from content.uploads import validate_pdf


class Command(BaseCommand):
    help = "Перенос исходного содержимого: только отсутствующие записи, без перезаписи правок редактора."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-dir",
            type=Path,
            default=settings.BASE_DIR / "public",
            help="Каталог исходных documents/ (до переключения сайта).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        source = options["source_dir"].resolve()
        data_dir = Path(__file__).resolve().parents[2] / "data"
        data = json.loads((data_dir / "legacy_content.json").read_text(encoding="utf-8"))
        # Validate all input before storing any file; absent existing files are never silently replaced.
        required = [(item["id"], "documents/materials/" + item["file"]) for item in data["documents"]]
        required += [(Path(item["href"]).stem, item["href"]) for item in data["complianceDocuments"]]
        for slug, relative in required:
            if Document.objects.filter(source_key=slug).exists():
                continue
            path = source / relative
            if not path.is_file():
                raise CommandError(f"Не найден исходный PDF: {path}")
            with path.open("rb") as stream:
                validate_pdf(File(stream, name=path.name))

        SiteSettings.objects.get_or_create(
            singleton=1,
            defaults={
                "company_name": "Дары Синергии",
                "legal_name": "ИП Бобко Роман Викторович",
                "email": "sintez2016@gmail.com",
                "phone": "+79060104066",
                "phone_label": "+7 (906) 010-40-66",
                "footer_label": "© 2026 «Дары Синергии» · ИП Бобко Роман Викторович",
            },
        )
        collections = {}
        for order, topic in enumerate(data["topics"]):
            collection, created = Collection.objects.get_or_create(
                source_key=topic["id"],
                defaults={
                    "slug": topic["id"],
                    "title": topic["title"],
                    "intro": topic["intro"],
                    "image_base": topic.get("image", ""),
                    "handbook_chapter": topic.get("chapter"),
                    "order": order,
                    "status": PublicationStatus.PUBLISHED,
                },
            )
            collections[topic["id"]] = collection
            if created:
                CollectionSection.objects.bulk_create(
                    [
                        CollectionSection(collection=collection, title=heading, body=copy, order=index)
                        for index, (heading, copy) in enumerate(topic["sections"])
                    ]
                )

        industries = {}
        for order, item in enumerate(data["contexts"]):
            label = (
                "Материалы о лошадях и КРС"
                if item["id"] == "agriculture"
                else "Материалы для спортивных клубов"
                if item["id"] == "sport"
                else "Материалы по направлению"
            )
            industry, _ = Industry.objects.get_or_create(
                source_key=item["id"],
                defaults={
                    "slug": item["id"],
                    "title": item["title"],
                    "caption": item["caption"],
                    "image_base": "context-" + item["id"],
                    "action_label": label,
                    "collection": collections[item["id"]],
                    "order": order,
                    "show_on_home": True,
                    "status": PublicationStatus.PUBLISHED,
                },
            )
            industries[item["id"]] = industry

        for order, item in enumerate(data["documents"]):
            doc, created = self._document(
                source,
                item["id"],
                "documents/materials/" + item["file"],
                {
                    "title": item["title"],
                    "description": item["description"],
                    "material_type": item["type"],
                    "pages": item["pages"],
                    "order": order,
                    "show_on_home": item["id"] == "handbook",
                },
            )
            if created:
                linked = [topic["id"] for topic in data["topics"] if item["id"] in topic["docs"]]
                doc.collections.set([collections[slug] for slug in linked])
                doc.industries.set([industries[slug] for slug in linked if slug in industries])

        for order, item in enumerate(data["complianceDocuments"]):
            self._document(
                source,
                Path(item["href"]).stem,
                item["href"],
                {
                    "title": item["title"],
                    "material_type": "Декларация соответствия",
                    "is_declaration": True,
                    "category": item["category"],
                    "registration": item["registration"],
                    "valid_until_label": item["validUntil"],
                    "order": order,
                    "show_on_home": True,
                },
            )

        for filename in ("materials_copy.json", "landing_copy.json"):
            path = data_dir / filename
            if path.exists():
                for key, value in json.loads(path.read_text(encoding="utf-8")).items():
                    SiteText.objects.get_or_create(
                        key=key, defaults={"label": str(value)[:200] or key, "value": value}
                    )
        stages = data_dir / "landing_stages.json"
        if stages.exists():
            for index, item in enumerate(json.loads(stages.read_text(encoding="utf-8")), 1):
                for field in ("title", "copy"):
                    SiteText.objects.get_or_create(
                        key=f"stage_{index}_{field}",
                        defaults={"label": f"Система: шаг {index}, {field}", "value": item[field]},
                    )
        self.stdout.write(
            self.style.SUCCESS(
                "Исходные записи добавлены. Существующие тексты, публикации и связи сохранены."
            )
        )

    def _document(self, source, slug, relative, defaults):
        existing = Document.objects.filter(source_key=slug).first()
        if existing:
            return existing, False
        doc = Document(source_key=slug, slug=slug, status=PublicationStatus.PUBLISHED, **defaults)
        with (source / relative).open("rb") as stream:
            doc.file.save(Path(relative).name, File(stream), save=False)
        doc.full_clean()
        doc.save()
        DocumentAlias.objects.get_or_create(path=relative, defaults={"document": doc})
        return doc, True
