import re
from django import forms
from .models import DeliveryMethod
from .phone import COUNTRIES


class PhoneCountrySelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value in COUNTRIES:
            code, length, _, _ = COUNTRIES[value]
            option["attrs"].update({"data-code": code, "data-length": length})
        return option


class CheckoutForm(forms.Form):
    first_name = forms.CharField(
        label="Имя", max_length=50, widget=forms.TextInput(attrs={"autocomplete": "given-name"})
    )
    last_name = forms.CharField(
        label="Фамилия", max_length=50, widget=forms.TextInput(attrs={"autocomplete": "family-name"})
    )
    middle_name = forms.CharField(
        label="Отчество",
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={"autocomplete": "additional-name"}),
    )
    phone_country = forms.ChoiceField(
        label="Код страны",
        initial="RU",
        choices=[(region, f"{flag} +{code} — {name}") for region, (code, _, flag, name) in COUNTRIES.items()],
        widget=PhoneCountrySelect(attrs={"autocomplete": "tel-country-code"}),
    )
    phone = forms.CharField(
        label="Телефон",
        max_length=32,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "tel-national",
                "type": "tel",
                "inputmode": "tel",
                "placeholder": "(917) 012-42-78",
                "aria-describedby": "phone-help",
            }
        ),
    )
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    delivery_method = forms.ModelChoiceField(
        label="Способ получения",
        queryset=DeliveryMethod.objects.filter(active=True),
        empty_label="Выберите способ получения",
    )
    address = forms.CharField(
        label="Адрес получения",
        required=False,
        max_length=1500,
        widget=forms.Textarea(attrs={"rows": 3, "autocomplete": "street-address"}),
        help_text="Укажите полный адрес для выбранного способа получения.",
    )
    comment = forms.CharField(
        label="Комментарий", required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3})
    )
    accept_terms = forms.BooleanField(label="Принимаю условия покупки")
    checkout_key = forms.UUIDField(widget=forms.HiddenInput)
    quote_token = forms.CharField(widget=forms.HiddenInput)
    confirmed_delivery = forms.IntegerField(required=False, widget=forms.HiddenInput)
    delivery_quote = forms.CharField(required=False, widget=forms.HiddenInput)
    pvz_code = forms.RegexField(
        r"^[A-Za-z0-9_-]{1,32}$",
        label="Код пункта СДЭК",
        max_length=32,
        required=False,
        help_text="Выберите пункт на карте или введите его код с сайта СДЭК.",
        widget=forms.HiddenInput,
        error_messages={"invalid": "Проверьте код пункта СДЭК."},
    )

    def clean_phone(self):
        value = self.cleaned_data["phone"].strip()
        country = self.cleaned_data.get("phone_country")
        if country not in COUNTRIES:
            return value
        code, length, _, _ = COUNTRIES[country]
        if not re.fullmatch(r"\+?[0-9 ()-]+", value):
            raise forms.ValidationError("Введите номер цифрами, без букв и добавочного номера.")
        digits = re.sub(r"[^0-9]", "", value)
        if value.startswith("+"):
            if not digits.startswith(code):
                raise forms.ValidationError("Код номера не совпадает с выбранной страной.")
            digits = digits[len(code) :]
        elif country in {"RU", "KZ"} and len(digits) == 11 and digits[0] in "78":
            digits = digits[1:]
        if len(digits) != length:
            raise forms.ValidationError(f"Введите {length} цифр номера после кода +{code}.")
        return f"+{code}{digits}"

    def clean(self):
        values = super().clean()
        if values.get("first_name") and values.get("last_name"):
            values["name"] = " ".join(
                values[key] for key in ("last_name", "first_name", "middle_name") if values.get(key)
            )
        method = values.get("delivery_method")
        if method and method.type == "static" and method.address_required and not values.get("address"):
            self.add_error("address", "Для выбранного способа получения укажите адрес.")
        if method and method.type == "cdek_pvz" and not values.get("delivery_quote"):
            self.add_error("pvz_code", "Выберите пункт выдачи и рассчитайте доставку перед оплатой.")
        return values
