import io
import tempfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import get_urlconf, set_urlconf
from django.utils import timezone
from PIL import Image

from .models import Collection, Document, Industry, PublicationStatus, SiteText, Video
from .uploads import validate_image, validate_pdf


class ImportedContentTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media = tempfile.TemporaryDirectory()
        cls.media_settings = override_settings(PRIVATE_MEDIA_ROOT=Path(cls.media.name))
        cls.media_settings.enable()

    @classmethod
    def tearDownClass(cls):
        cls.media_settings.disable()
        cls.media.cleanup()
        super().tearDownClass()

    def setUp(self):
        call_command("import_legacy_content", stdout=io.StringIO())
        self.client.defaults["HTTP_HOST"] = settings.MAIN_HOST

    def test_import_complete_and_repeated_import_preserves_editorial_changes(self):
        self.assertEqual(Industry.objects.count(), 5)
        self.assertEqual(Collection.objects.count(), 8)
        self.assertEqual(Document.objects.filter(is_declaration=False).count(), 12)
        self.assertEqual(Document.objects.filter(is_declaration=True).count(), 3)
        document = Document.objects.get(source_key="oil")
        original_file = document.file.name
        document.title = "Уточнённое редактором название"
        document.slug = "edited-oil"
        document.status = PublicationStatus.DRAFT
        document.save()
        document.collections.clear()
        collection = Collection.objects.get(source_key="sport")
        collection.slug = "sports-centers"
        collection.save()
        text = SiteText.objects.get(key="materials_title")
        text.value = "Редакторская библиотека"
        text.save()
        call_command("import_legacy_content", stdout=io.StringIO())
        document.refresh_from_db()
        self.assertEqual(Document.objects.count(), 15)
        self.assertEqual(Collection.objects.count(), 8)
        self.assertEqual(document.title, "Уточнённое редактором название")
        self.assertEqual(document.status, PublicationStatus.DRAFT)
        self.assertEqual(document.collections.count(), 0)
        self.assertEqual(document.file.name, original_file)
        self.assertEqual(SiteText.objects.get(pk=text.pk).value, "Редакторская библиотека")

    def test_every_imported_file_has_safe_name_and_working_guarded_url(self):
        for document in Document.objects.all():
            self.assertRegex(document.file.name, r"^content/document/[a-f0-9]{32}\.pdf$")
            self.assertTrue(document.file.storage.exists(document.file.name))
            response = self.client.get(document.file_url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertIn("no-store", response["Cache-Control"])
            response.close()
            with self.assertRaises(ValueError):
                document.file.url

    def test_drafts_unavailable_in_pages_fragments_downloads_and_legacy_routes(self):
        document = Document.objects.get(source_key="oil")
        document.title = "Закрытый документ для проверки публикации"
        document.status = PublicationStatus.DRAFT
        document.save()
        for headers in ({}, {"HTTP_HX_REQUEST": "true"}):
            self.assertNotContains(self.client.get("/materials/", **headers), document.title)
        self.assertEqual(self.client.get(document.file_url).status_code, 404)
        self.assertEqual(self.client.get(document.file_url + "?download=1").status_code, 404)
        self.assertEqual(self.client.get("/documents/materials/ozonated-oil.pdf").status_code, 404)
        collection = Collection.objects.get(source_key="sport")
        collection.status = PublicationStatus.ARCHIVED
        collection.save()
        self.assertEqual(self.client.get(collection.get_absolute_url()).status_code, 404)
        self.assertEqual(
            self.client.get(collection.get_absolute_url(), HTTP_HX_REQUEST="true").status_code, 404
        )

    def test_changed_addresses_preserve_old_document_and_collection_links(self):
        document = Document.objects.get(source_key="handbook")
        old_url = document.file_url
        document.slug = "updated-handbook"
        document.save()
        self.assertRedirects(
            self.client.get(old_url), document.file_url, status_code=301, fetch_redirect_response=False
        )
        self.assertRedirects(
            self.client.get("/documents/materials/ozone-handbook.pdf"),
            document.file_url,
            status_code=301,
            fetch_redirect_response=False,
        )
        self.assertContains(self.client.get("/"), document.file_url)
        collection = Collection.objects.get(source_key="sport")
        old_url = collection.get_absolute_url()
        collection.slug = "sports-centers"
        collection.save()
        self.assertRedirects(
            self.client.get(old_url),
            collection.get_absolute_url(),
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_filter_preserves_url_full_html_and_history_restore_contract(self):
        response = self.client.get("/materials/?direction=hydrolats")
        self.assertContains(response, "Гидролаты: краткий гид")
        self.assertContains(response, "Полный справочник по применению озона")
        self.assertNotContains(response, "Озонированные ванны для человека")
        self.assertContains(response, 'value="hydrolats" selected')
        self.assertIn("HX-Request", response["Vary"])
        fragment = self.client.get("/materials/", HTTP_HX_REQUEST="true")
        self.assertNotContains(fragment, "<!doctype html>", html=False)
        self.assertTemplateUsed(fragment, "site/partials/materials_content.html")
        restored = self.client.get(
            "/materials/", HTTP_HX_REQUEST="true", HTTP_HX_HISTORY_RESTORE_REQUEST="true"
        )
        self.assertTemplateUsed(restored, "site/base.html")
        self.assertEqual(self.client.get("/materials/no-such-topic/").status_code, 404)

    def test_future_publication_is_hidden_and_editorial_markup_is_escaped(self):
        document = Document.objects.get(source_key="oil")
        document.title = '<script>alert("unsafe")</script>'
        document.save()
        self.assertContains(self.client.get("/materials/"), "&lt;script&gt;")
        self.assertNotContains(self.client.get("/materials/"), document.title)
        document.published_at = timezone.now() + timedelta(days=1)
        document.save()
        self.assertEqual(self.client.get(document.file_url).status_code, 404)

    def test_closed_admin_preview_enforces_permissions_and_does_not_publish(self):
        doc = Document.objects.get(source_key="oil")
        doc.status = PublicationStatus.DRAFT
        doc.save()
        preview = f"/admin/content/document/{doc.pk}/preview/"
        user = get_user_model().objects.create_user("editor", password="test-editor-password", is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(preview, HTTP_HOST=settings.SHOP_HOST).status_code, 403)
        user.user_permissions.add(
            Permission.objects.get(codename="view_document", content_type__app_label="content")
        )
        response = self.client.get(preview, HTTP_HOST=settings.SHOP_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(
            self.client.get(
                f"/admin/content/document/{doc.pk}/change/", HTTP_HOST=settings.SHOP_HOST
            ).status_code,
            200,
        )
        private_file = self.client.get(preview + "file/", HTTP_HOST=settings.SHOP_HOST)
        self.assertEqual(private_file.status_code, 200)
        private_file.close()
        self.assertEqual(self.client.get(doc.file_url).status_code, 404)


class UploadValidationTests(TestCase):
    def test_pdf_requires_actual_pdf_and_limit(self):
        with self.assertRaises(ValidationError):
            validate_pdf(SimpleUploadedFile("fake.pdf", b"<html>not a pdf</html>"))
        with self.assertRaises(ValidationError):
            validate_pdf(SimpleUploadedFile("evil.svg", b"%PDF-1.4\n"))
        with override_settings(CONTENT_DOCUMENT_MAX_BYTES=5), self.assertRaises(ValidationError):
            validate_pdf(SimpleUploadedFile("large.pdf", b"%PDF-1.4\n"))

    def test_image_extension_and_actual_format_must_match(self):
        stream = io.BytesIO()
        Image.new("RGB", (2, 2)).save(stream, format="PNG")
        validate_image(SimpleUploadedFile("logo.png", stream.getvalue()))
        with self.assertRaises(ValidationError):
            validate_image(SimpleUploadedFile("logo.jpg", stream.getvalue()))
        with self.assertRaises(ValidationError):
            validate_image(SimpleUploadedFile("logo.svg", b"<svg onload='bad()'/>"))

    def test_video_provider_needs_approval_and_rejects_iframe(self):
        video = Video(
            title="Редакторское видео",
            provider="rutube",
            provider_id='<iframe src="https://example.com"></iframe>',
        )
        with self.assertRaises(ValidationError):
            video.full_clean()
        video.provider_id = "a123b456"
        video.status = PublicationStatus.PUBLISHED
        with override_settings(CONTENT_VIDEO_PROVIDERS=()), self.assertRaises(ValidationError):
            video.full_clean()


@override_settings(CONTENT_VIDEO_PROVIDERS=("rutube",))
class ShopEditorialIntegrationTests(TestCase):
    def setUp(self):
        from datetime import date
        from catalog.models import Product
        from reviews.models import Review

        self.media = tempfile.TemporaryDirectory()
        self.media_settings = override_settings(PRIVATE_MEDIA_ROOT=Path(self.media.name))
        self.media_settings.enable()
        self.addCleanup(self.media.cleanup)
        self.addCleanup(self.media_settings.disable)
        call_command("import_legacy_content", stdout=io.StringIO())
        self.product = Product.objects.create(
            name="Тест связей с CMS", slug="cms-integration-test", sku="TEST-CMS", status="published"
        )
        self.document = Document.objects.get(source_key="oil")
        self.document.products.add(self.product)
        self.hidden_document = Document.objects.get(source_key="safety")
        self.hidden_document.title = "Скрытый тестовый PDF"
        self.hidden_document.status = PublicationStatus.DRAFT
        self.hidden_document.save()
        self.hidden_document.products.add(self.product)
        stream = io.BytesIO()
        Image.new("RGB", (2, 2)).save(stream, format="PNG")
        self.review = Review.objects.create(
            author="Тестовый автор CMS",
            organization="Тестовая организация",
            text="Тестовый длинный отзыв. " * 40,
            date=date(2026, 9, 11),
            publication_basis="Основание тестового отзыва",
            status=PublicationStatus.PUBLISHED,
            photo=SimpleUploadedFile("test-review.png", stream.getvalue(), content_type="image/png"),
        )
        self.review.products.add(self.product)
        self.hidden_review = Review.objects.create(
            author="Скрытый тестовый автор", text="Скрытый текст отзыва", date=date(2026, 9, 11)
        )
        self.hidden_review.products.add(self.product)
        self.video = Video.objects.create(
            title="Тестовое видео CMS",
            provider="rutube",
            provider_id="test1234",
            status=PublicationStatus.PUBLISHED,
            cover=SimpleUploadedFile("test-cover.png", stream.getvalue(), content_type="image/png"),
        )
        self.video.products.add(self.product)
        self.hidden_video = Video.objects.create(
            title="Скрытое тестовое видео", provider="rutube", provider_id="hidden1234"
        )
        self.hidden_video.products.add(self.product)

    def test_public_cms_urls_resolve_when_current_urlconf_is_shop(self):
        current_urlconf = get_urlconf()
        try:
            set_urlconf("config.shop_urls")
            self.assertEqual(self.document.file_url, "/documents/oil/")
            self.assertEqual(self.document.get_absolute_url(), "/documents/oil/")
            self.assertEqual(
                Collection.objects.get(source_key="sport").get_absolute_url(), "/materials/sport/"
            )
            self.assertEqual(self.review.photo_url, f"/media/reviews/{self.review.pk}/")
            self.assertEqual(self.video.cover_url, f"/media/videos/{self.video.pk}/")
        finally:
            set_urlconf(current_urlconf)

    def test_product_full_and_fragment_show_only_published_editorial_records(self):
        for headers in ({}, {"HTTP_HX_REQUEST": "true"}):
            response = self.client.get(
                self.product.get_absolute_url(), HTTP_HOST=settings.SHOP_HOST, **headers
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, self.document.title)
            self.assertContains(response, settings.MAIN_ORIGIN + self.document.file_url)
            self.assertContains(response, self.review.author)
            self.assertContains(response, self.review.organization)
            self.assertContains(response, "Читать полностью")
            self.assertContains(response, settings.MAIN_ORIGIN + self.review.photo_url)
            self.assertContains(response, self.video.title)
            self.assertContains(response, self.video.external_url)
            self.assertContains(response, settings.MAIN_ORIGIN + self.video.cover_url)
            self.assertNotContains(response, self.hidden_document.title)
            self.assertNotContains(response, self.hidden_review.author)
            self.assertNotContains(response, self.hidden_video.title)
        policy = response.get("Content-Security-Policy", "")
        image_rule = next((rule for rule in policy.split(";") if rule.strip().startswith("img-src ")), "")
        self.assertIn(settings.MAIN_ORIGIN, image_rule)

    def test_archiving_editorial_media_closes_public_downloads_and_shop_links(self):
        for item, path in (
            (self.document, self.document.file_url),
            (self.review, self.review.photo_url),
            (self.video, self.video.cover_url),
        ):
            response = self.client.get(path, HTTP_HOST=settings.MAIN_HOST)
            self.assertEqual(response.status_code, 200)
            response.close()
            item.status = PublicationStatus.ARCHIVED
            item.save()
            self.assertEqual(self.client.get(path, HTTP_HOST=settings.MAIN_HOST).status_code, 404)
            self.assertEqual(
                self.client.get(path, HTTP_HOST=settings.MAIN_HOST, HTTP_HX_REQUEST="true").status_code, 404
            )
        response = self.client.get(self.product.get_absolute_url(), HTTP_HOST=settings.SHOP_HOST)
        self.assertNotContains(response, self.document.file_url)
        self.assertNotContains(response, self.review.author)
        self.assertNotContains(response, self.video.title)
