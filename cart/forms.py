from django import forms


class QuantityForm(forms.Form):
    quantity = forms.IntegerField(label="Количество", min_value=1, max_value=999, initial=1)
