import io
import json
import re
import tempfile
from html import unescape
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings

from .models import Collection, CollectionAlias, Document, Industry, SiteSettings, SiteText


class SEOReleaseTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        storage = override_settings(PRIVATE_MEDIA_ROOT=Path(media.name))
        storage.enable()
        self.addCleanup(media.cleanup)
        self.addCleanup(storage.disable)
        call_command("import_legacy_content", stdout=io.StringIO())
        self.client.defaults["HTTP_HOST"] = settings.MAIN_HOST

    def apply(self, **kwargs):
        output = io.StringIO()
        call_command("apply_seo_content", stdout=output, **kwargs)
        return output.getvalue()

    def schema(self, response):
        match = re.search(
            r'<script id="page-structured-data" type="application/ld\+json">(.*?)</script>',
            response.content.decode(),
            re.S,
        )
        self.assertIsNotNone(match)
        return json.loads(match[1])

    def test_pdf_canonical_preserves_download_and_publication_guards(self):
        doc = Document.objects.get(source_key="oil-guide")
        expected = f'<{settings.MAIN_ORIGIN}{doc.file_url}>; rel="canonical"'
        for query in ("", "?download=1", "?utm_source=check"):
            response = self.client.get(doc.file_url + query)
            self.assertEqual(response["Link"], expected)
            self.assertEqual(response["Content-Security-Policy"], "default-src 'none'; sandbox")
            self.assertIn("no-store", response["Cache-Control"])
            self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))
            if query == "?download=1":
                self.assertIn("attachment", response["Content-Disposition"])
        doc.status = "draft"
        doc.save()
        response = self.client.get(doc.file_url + "?download=1")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("Link", response)

    def test_schema_uses_live_company_settings_and_escapes_script_breakouts(self):
        company = SiteSettings.objects.get()
        company.company_name = '</script><img src=x onerror="alert(1)">'
        company.email = "editor@example.test"
        company.phone = ""
        company.save()
        response = self.client.get("/")
        schema = self.schema(response)
        self.assertEqual(schema["@type"], "Organization")
        self.assertEqual(schema["name"], company.company_name)
        self.assertEqual(schema["email"], company.email)
        self.assertNotIn("telephone", schema)
        self.assertTrue(schema["logo"].startswith(settings.MAIN_ORIGIN + "/static/"))
        self.assertNotContains(response, company.company_name)
        transport = re.search(r'data-structured-data="([^"]*)"', response.content.decode())[1]
        self.assertEqual(json.loads(unescape(transport)), schema)

    def test_breadcrumbs_follow_renamed_collection_and_noindex_gate(self):
        topic = Collection.objects.get(source_key="oils")
        topic.slug = "new-oils"
        topic.title = 'Масла "редакторские"'
        topic.save()
        response = self.client.get(topic.get_absolute_url())
        schema = self.schema(response)
        self.assertEqual(schema["@type"], "BreadcrumbList")
        self.assertEqual(
            schema["itemListElement"][-1],
            {
                "@type": "ListItem",
                "position": 3,
                "name": topic.title,
                "item": settings.MAIN_ORIGIN + topic.get_absolute_url(),
            },
        )
        self.assertContains(response, 'aria-label="Хлебные крошки"')
        fragment = self.client.get(topic.get_absolute_url(), HTTP_HX_REQUEST="true")
        transport = re.search(r'data-structured-data="([^"]*)"', fragment.content.decode())[1]
        self.assertEqual(json.loads(unescape(transport)), schema)
        with override_settings(SITE_INDEXING_ENABLED=False):
            response = self.client.get(topic.get_absolute_url())
            self.assertNotContains(response, 'type="application/ld+json"')
            self.assertContains(response, 'data-structured-data=""')
            self.assertIn("noindex", response["X-Robots-Tag"])

    def test_content_preview_is_read_only_and_apply_is_idempotent(self):
        before = list(Collection.objects.values("id", "title", "intro"))
        self.apply()
        self.assertEqual(before, list(Collection.objects.values("id", "title", "intro")))
        self.assertEqual(Collection.objects.count(), 8)
        self.apply(apply=True)
        water = Collection.objects.get(source_key="seo-water-systems-20260921")
        self.assertEqual(water.sections.count(), 6)
        self.assertEqual(Industry.objects.filter(collection=water).count(), 5)
        self.assertIn(water.get_absolute_url(), self.client.get("/sitemap.xml").content.decode())
        page = self.client.get(water.get_absolute_url())
        self.assertContains(page, "Что подготовить для консультации")
        self.assertContains(page, "/documents/ozone-generator-declaration/")
        self.assertNotContains(page, "В этой подборке пока нет опубликованных документов")
        sections = list(Collection.objects.get(source_key="oils").sections.values_list("pk", "body"))
        self.apply(apply=True)
        self.assertEqual(Collection.objects.count(), 9)
        self.assertEqual(
            sections, list(Collection.objects.get(source_key="oils").sections.values_list("pk", "body"))
        )

    def test_content_update_preserves_editor_fields_sections_and_links(self):
        oil = Collection.objects.get(source_key="oils")
        section = oil.sections.first()
        section.body = "Подтверждённый текст клиента"
        section.save()
        sport = Industry.objects.get(source_key="sport")
        sport.action_label = "Своя подпись"
        sport.save()
        text = SiteText.objects.get(key="home_meta_description")
        text.value = "Описание клиента"
        text.save()
        self.apply(apply=True)
        section.refresh_from_db()
        sport.refresh_from_db()
        text.refresh_from_db()
        self.assertEqual(section.body, "Подтверждённый текст клиента")
        self.assertEqual(oil.sections.count(), 2)
        self.assertEqual(sport.action_label, "Своя подпись")
        self.assertEqual(sport.collection.source_key, "sport")
        self.assertEqual(text.value, "Описание клиента")

    def test_new_page_never_steals_an_alias_or_republishes_a_draft(self):
        topic = Collection.objects.get(source_key="family")
        alias = CollectionAlias.objects.create(slug="water-systems", collection=topic)
        output = self.apply(apply=True)
        self.assertIn("адрес занят", output)
        self.assertFalse(Collection.objects.filter(source_key="seo-water-systems-20260921").exists())
        self.assertEqual(Industry.objects.get(source_key="family").collection_id, topic.pk)
        alias.delete()
        self.apply(apply=True)
        water = Collection.objects.get(source_key="seo-water-systems-20260921")
        water.status = "draft"
        water.save()
        self.apply(apply=True)
        water.refresh_from_db()
        self.assertEqual(water.status, "draft")
        self.assertEqual(self.client.get(water.get_absolute_url()).status_code, 404)
