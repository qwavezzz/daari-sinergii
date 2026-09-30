from io import StringIO
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from .models import Document, FAQEntry, SiteSettings
from .customer_content import CUSTOMER_PAGES
from orders.models import StoreSettings, DeliveryMethod


class CustomerPagesTests(TestCase):
    def setUp(self):
        call_command("setup_customer_pages", stdout=StringIO())

    def test_all_seven_pages_are_html_on_both_hosts_and_have_shared_links(self):
        for host in ("localhost", "shop.localhost"):
            for title, path, field in CUSTOMER_PAGES.values():
                with self.subTest(host=host, path=path):
                    response = self.client.get(path, HTTP_HOST=host)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("text/html", response["Content-Type"])
                    self.assertContains(response, title)
                    self.assertContains(response, 'href="/contacts/"')
                    self.assertContains(response, 'href="/faq/"')
                    self.assertNotContains(response, "Документ готовится")
                    self.assertNotContains(response, "{delivery_price}")
                    self.assertNotContains(response, "{legal_name}")

    def test_contact_fields_and_text_are_editable_without_template_execution(self):
        site = SiteSettings.objects.get()
        site.inn = "123456789012"
        site.registration_number = "123456789012345"
        site.return_address = "Тестовый адрес возврата"
        site.save()
        StoreSettings.objects.update(
            contacts_text="Обновлённый текст <script>alert(1)</script> {{ request }}"
        )
        response = self.client.get("/contacts/", HTTP_HOST="shop.localhost")
        self.assertContains(response, site.inn)
        self.assertContains(response, site.registration_number)
        self.assertContains(response, site.return_address)
        self.assertContains(response, "Обновлённый текст")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "{{ request }}")

    def test_faq_respects_publication_order_and_updated_delivery_price(self):
        DeliveryMethod.objects.update(price=Decimal("450.50"))
        FAQEntry.objects.create(question="Скрытый вопрос", answer="Не показывать", active=False)
        FAQEntry.objects.create(question="Вопрос владельца", answer="Ответ владельца", order=99)
        response = self.client.get("/faq/", HTTP_HOST="localhost")
        self.assertContains(response, "450,50")
        self.assertNotContains(response, "Скрытый вопрос")
        self.assertContains(response, "Ответ владельца")
        self.assertNotContains(response, "300 ₽")

    def test_only_current_published_declarations_are_listed(self):
        for slug, status, declaration, date in [
            ("visible", "published", True, timezone.now()),
            ("draft", "draft", True, None),
            ("future", "published", True, timezone.now() + timedelta(days=2)),
            ("presentation", "published", False, timezone.now()),
        ]:
            Document.objects.create(
                slug=slug,
                title="Document " + slug,
                status=status,
                published_at=date,
                is_declaration=declaration,
                file="test.pdf",
                registration="TEST-REG",
                material_type="Декларация",
            )
        response = self.client.get("/product-documents/", HTTP_HOST="localhost")
        self.assertContains(response, "Document visible")
        self.assertContains(response, "TEST-REG")
        for hidden in ("draft", "future", "presentation"):
            self.assertNotContains(response, "Document " + hidden)

    def test_setup_preserves_owner_edits_tariff_and_checkout_flag(self):
        StoreSettings.objects.update(terms_text="Редакция владельца", checkout_enabled=False)
        DeliveryMethod.objects.update(price=Decimal("450.00"), active=False)
        count = FAQEntry.objects.count()
        call_command("setup_customer_pages", stdout=StringIO())
        self.assertEqual(StoreSettings.objects.get().terms_text, "Редакция владельца")
        self.assertFalse(StoreSettings.objects.get().checkout_enabled)
        self.assertEqual(DeliveryMethod.objects.get().price, Decimal("450.00"))
        self.assertFalse(DeliveryMethod.objects.get().active)
        self.assertEqual(FAQEntry.objects.count(), count)

    def test_admin_can_edit_contacts_pages_and_faq(self):
        user = get_user_model().objects.create_superuser("owner", "owner@example.test", "test-password")
        self.client.force_login(user)
        cases = [
            ("content/sitesettings", SiteSettings.objects.get(), "registration_number"),
            ("orders/storesettings", StoreSettings.objects.get(), "returns_text"),
            ("content/faqentry", FAQEntry.objects.first(), "answer"),
            ("orders/deliverymethod", DeliveryMethod.objects.get(), "price"),
        ]
        for model, obj, field in cases:
            response = self.client.get(f"/admin/{model}/{obj.pk}/change/", HTTP_HOST="shop.localhost")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f'name="{field}"')

    def test_main_sitemap_and_partial_navigation(self):
        response = self.client.get("/sitemap.xml", HTTP_HOST="localhost")
        self.assertContains(response, "/product-documents/")
        response = self.client.get("/faq/", HTTP_HOST="shop.localhost", HTTP_HX_REQUEST="true")
        self.assertContains(response, "Как оформить заказ?")
        self.assertNotContains(response, "<!doctype")

    def test_admin_price_save_updates_public_text_and_rejects_negative_price(self):
        owner = get_user_model().objects.create_superuser(
            "price-owner", "owner@example.test", "test-password"
        )
        self.client.force_login(owner)
        method = DeliveryMethod.objects.get()
        url = f"/admin/orders/deliverymethod/{method.pk}/change/"
        payload = {
            "name": method.name,
            "slug": method.slug,
            "price": "450.50",
            "active": "on",
            "address_required": "on",
            "is_default": "on",
            "sort_order": "0",
            "vat_code": "1",
            "_save": "Save",
        }
        response = self.client.post(url, payload, HTTP_HOST="shop.localhost")
        self.assertEqual(response.status_code, 302)
        method.refresh_from_db()
        self.assertEqual(method.price, Decimal("450.50"))
        self.assertContains(self.client.get("/delivery-and-payment/", HTTP_HOST="localhost"), "450,50")
        response = self.client.post(url, {**payload, "price": "-100"}, HTTP_HOST="shop.localhost")
        self.assertEqual(response.status_code, 200)
        method.refresh_from_db()
        self.assertEqual(method.price, Decimal("450.50"))
