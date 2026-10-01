import re
from django import forms
from .models import DeliveryMethod


class CheckoutForm(forms.Form):
    name = forms.CharField(
        label="Имя получателя", max_length=160, widget=forms.TextInput(attrs={"autocomplete": "name"})
    )
    phone = forms.CharField(
        label="Телефон", max_length=32, widget=forms.TextInput(attrs={"autocomplete": "tel", "type": "tel"})
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
        error_messages={"invalid": "Проверьте код пункта СДЭК."},
    )

    def clean_phone(self):
        value = self.cleaned_data["phone"].strip()
        if not re.fullmatch(r"[+\d ()-]+", value) or not 10 <= len(re.sub(r"\D", "", value)) <= 15:
            raise forms.ValidationError("Введите телефон с кодом страны.")
        return value

    def clean(self):
        values = super().clean()
        method = values.get("delivery_method")
        if method and method.type == "static" and method.address_required and not values.get("address"):
            self.add_error("address", "Для выбранного способа получения укажите адрес.")
        if method and method.type == "cdek_pvz" and not values.get("delivery_quote"):
            self.add_error("pvz_code", "Выберите пункт выдачи и рассчитайте доставку перед оплатой.")
        return values
