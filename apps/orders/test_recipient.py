from django.test import TestCase

from .forms import CheckoutForm
from .test_support import checkout_data, fixture_cart


class RecipientTests(TestCase):
    def setUp(self):
        self.cart, self.product, self.method = fixture_cart()
        self.data = checkout_data(self.cart, self.method)
        self.data["delivery_method"] = self.method.pk

    def form(self, **changes):
        return CheckoutForm({**self.data, **changes})

    def test_separate_names_are_required_and_middle_name_is_optional(self):
        for missing in ("first_name", "last_name"):
            with self.subTest(field=missing):
                form = self.form(**{missing: "  ", "name": "Старое единое поле"})
                self.assertFalse(form.is_valid())
                self.assertIn(missing, form.errors)
        form = self.form(first_name=" Анна-Мария ", last_name=" О’Нил ", middle_name="")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["name"], "О’Нил Анна-Мария")
        form = self.form(first_name="Иван", last_name="Иванов", middle_name="Иванович")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["name"], "Иванов Иван Иванович")

    def test_phone_normalizes_national_and_full_numbers(self):
        cases = [
            ("RU", "(917) 012-42-78", "+79170124278"),
            ("RU", "+7 (917) 012-42-78", "+79170124278"),
            ("RU", "8 (917) 012-42-78", "+79170124278"),
            ("KZ", "7012345678", "+77012345678"),
            ("BY", "29 123-45-67", "+375291234567"),
            ("AM", "77123456", "+37477123456"),
        ]
        for country, phone, expected in cases:
            with self.subTest(country=country, phone=phone):
                form = self.form(phone_country=country, phone=phone)
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["phone"], expected)

    def test_cannot_bypass_phone_limits_or_country_with_direct_post(self):
        for country, phone in [
            ("RU", "91701242789"),
            ("RU", "917012427"),
            ("RU", "+375291234567"),
            ("BY", "2912345678"),
            ("RU", "9170124278 доб. 12"),
            ("RU", "٩١٧٠١٢٤٢٧٨"),
            ("XX", "9170124278"),
        ]:
            with self.subTest(country=country, phone=phone):
                self.assertFalse(self.form(phone_country=country, phone=phone).is_valid())
