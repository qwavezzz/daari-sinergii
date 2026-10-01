from io import StringIO
import hashlib
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from .models import Document, FAQEntry, SiteSettings
from .customer_content import CUSTOMER_PAGES, customer_sales_available
from .management.commands.setup_customer_pages import load_customer_copy
from apps.orders.models import StoreSettings, DeliveryMethod


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

    def test_faq_respects_publication_order_and_explains_dynamic_delivery(self):
        DeliveryMethod.objects.update(price=Decimal("450.50"))
        FAQEntry.objects.create(question="Скрытый вопрос", answer="Не показывать", active=False)
        FAQEntry.objects.create(question="Вопрос владельца", answer="Ответ владельца", order=99)
        response = self.client.get("/faq/", HTTP_HOST="localhost")
        self.assertContains(response, "Стоимость СДЭК рассчитывается после выбора пункта выдачи")
        self.assertNotContains(response, "450,50")
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
            "type": "static",
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

    def test_new_setup_does_not_invent_seller_or_enable_services(self):
        self.assertEqual(SiteSettings.objects.get().legal_name, "")
        method = DeliveryMethod.objects.get()
        self.assertEqual(method.type, "cdek_pvz")
        self.assertFalse(method.active)
        self.assertFalse(StoreSettings.objects.get().checkout_enabled)
        response = self.client.get("/contacts/", HTTP_HOST="shop.localhost")
        self.assertContains(response, "Сведения о продавце и адрес возврата уточняются")
        self.assertNotContains(response, "готовится к запуску")
        self.assertNotContains(response, "Онлайн-покупка пока недоступна")

    def test_dynamic_delivery_never_displays_placeholder_price_as_free_or_fixed(self):
        for price in (Decimal("0"), Decimal("300")):
            DeliveryMethod.objects.update(active=True, price=price)
            response = self.client.get("/delivery-and-payment/", HTTP_HOST="shop.localhost")
            self.assertContains(response, "Расчёт после выбора пункта выдачи")
            self.assertNotContains(response, "₽ за заказ")
            self.assertContains(response, "Отсутствие цены не означает бесплатную доставку")

    @override_settings(
        CHECKOUT_ENABLED=True,
        PAYMENT_STUB_ENABLED=True,
        ALFABANK_ENABLED=False,
        ALFABANK_TEST_MODE=True,
        CDEK_ENABLED=True,
        CDEK_TEST_MODE=True,
    )
    def test_trial_checkout_is_available_without_claiming_real_payment(self):
        StoreSettings.objects.update(checkout_enabled=True)
        DeliveryMethod.objects.update(active=True)
        response = self.client.get("/legal/terms/", HTTP_HOST="shop.localhost")
        self.assertTrue(response.context["customer_sales_available"])
        self.assertContains(response, "Пробная оплата: карта не нужна, деньги не списываются")
        self.assertNotContains(response, "Онлайн-покупка пока недоступна")
        self.assertNotContains(response, "после запуска")

    def test_order_availability_tracks_checkout_requirements(self):
        store = StoreSettings.objects.get()
        self.assertFalse(customer_sales_available(store))
        store.checkout_enabled = True
        self.assertFalse(customer_sales_available(store))
        DeliveryMethod.objects.update(active=True)
        with override_settings(CHECKOUT_ENABLED=True):
            self.assertTrue(customer_sales_available(store))
        with override_settings(CHECKOUT_ENABLED=False):
            self.assertFalse(customer_sales_available(store))
        store.privacy_text = ""
        self.assertFalse(customer_sales_available(store))

    @override_settings(PAYMENT_STUB_ENABLED=False)
    def test_customer_documents_stay_readable_without_trial_banner(self):
        for host in ("localhost", "shop.localhost"):
            for _, path, _ in CUSTOMER_PAGES.values():
                response = self.client.get(path, HTTP_HOST=host)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "Пробная оплата: карта не нужна")
                self.assertNotContains(response, "готовится к запуску")
                self.assertNotContains(response, "после запуска")

    def test_recent_standard_faq_refreshes_and_older_hashes_are_retained(self):
        data, previous = load_customer_copy()
        question = "Куда доставляется заказ?"
        old_answer = (
            "После подключения СДЭК — из Тольятти до выбранного доступного пункта выдачи в России. "
            "Сайт проверяет возможность приёма отправления выбранным пунктом."
        )
        self.assertIn(hashlib.sha256(old_answer.encode()).hexdigest(), previous["faq"][question])
        self.assertIn(
            "20d18e5702431be9b00a8e74a754d19907e32413dca75d7115c15b8266f0f23f",
            previous["faq"][question],
        )
        FAQEntry.objects.filter(question=question).update(answer=old_answer)
        edited = FAQEntry.objects.exclude(question=question).first()
        edited.answer = "Ответ владельца"
        edited.save(update_fields=["answer"])
        call_command("setup_customer_pages", refresh_defaults=True, stdout=StringIO())
        self.assertEqual(FAQEntry.objects.get(question=question).answer, dict(data["faq"])[question])
        edited.refresh_from_db()
        self.assertEqual(edited.answer, "Ответ владельца")

    def test_refresh_updates_only_matching_seed_and_preserves_editor_and_contacts(self):
        data, previous = load_customer_copy()
        old_text = "Предыдущий стандартный текст"
        previous["pages"]["delivery_text"] = ["older-baseline", hashlib.sha256(old_text.encode()).hexdigest()]
        question, _ = data["faq"][1]
        previous["faq"][question] = hashlib.sha256(old_text.encode()).hexdigest()
        StoreSettings.objects.update(delivery_text=old_text, terms_text="Условия редактора")
        SiteSettings.objects.update(legal_name="Подтверждённый продавец", email="owner@example.test")
        FAQEntry.objects.filter(question=question).update(answer=old_text, active=False, order=99)
        method = DeliveryMethod.objects.get()
        method.active = True
        method.price = Decimal("450")
        method.save()
        loader = "apps.content.management.commands.setup_customer_pages.load_customer_copy"
        with patch(loader, return_value=(data, previous)):
            call_command("setup_customer_pages", refresh_defaults=True, dry_run=True, stdout=StringIO())
            self.assertEqual(StoreSettings.objects.get().delivery_text, old_text)
            self.assertEqual(FAQEntry.objects.get(question=question).answer, old_text)
            call_command("setup_customer_pages", refresh_defaults=True, stdout=StringIO())
        store = StoreSettings.objects.get()
        self.assertEqual(store.delivery_text, data["pages"]["delivery_text"])
        self.assertEqual(store.terms_text, "Условия редактора")
        self.assertFalse(store.checkout_enabled)
        site = SiteSettings.objects.get()
        self.assertEqual(site.legal_name, "Подтверждённый продавец")
        self.assertEqual(site.email, "owner@example.test")
        entry = FAQEntry.objects.get(question=question)
        self.assertEqual(entry.answer, dict(data["faq"])[question])
        self.assertFalse(entry.active)
        self.assertEqual(entry.order, 99)
        method.refresh_from_db()
        self.assertEqual(method.price, Decimal("450"))
        self.assertTrue(method.active)

    def test_dry_run_on_empty_database_does_not_create_rows(self):
        StoreSettings.objects.all().delete()
        SiteSettings.objects.all().delete()
        FAQEntry.objects.all().delete()
        DeliveryMethod.objects.all().delete()
        call_command("setup_customer_pages", dry_run=True, stdout=StringIO())
        for model in (StoreSettings, SiteSettings, FAQEntry, DeliveryMethod):
            self.assertFalse(model.objects.exists())

    def test_refresh_does_not_recreate_deleted_faq(self):
        FAQEntry.objects.all().delete()
        call_command("setup_customer_pages", refresh_defaults=True, stdout=StringIO())
        self.assertFalse(FAQEntry.objects.exists())
