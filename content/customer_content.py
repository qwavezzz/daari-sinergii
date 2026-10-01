"""Plain text authored in admin; only named business values are substituted, never template code."""

import re

from django.conf import settings
from orders.delivery import default_delivery
from orders.models import DeliveryMethod
from .models import SiteSettings


CUSTOMER_PAGES = {
    "privacy": ("Политика обработки персональных данных", "/legal/privacy/", "privacy_text"),
    "terms": ("Условия покупки", "/legal/terms/", "terms_text"),
    "delivery": ("Доставка и оплата", "/delivery-and-payment/", "delivery_text"),
    "returns": ("Возврат и отмена заказа", "/returns/", "returns_text"),
    "contacts": ("Контакты и реквизиты", "/contacts/", "contacts_text"),
    "documents": ("Документы на продукцию", "/product-documents/", "documents_text"),
    "faq": ("Вопросы и ответы", "/faq/", "faq_text"),
}


def customer_links():
    return [{"key": key, "title": row[0], "url": row[1]} for key, row in CUSTOMER_PAGES.items()]


def text_values():
    site = SiteSettings.objects.first()
    method = default_delivery()
    values = {
        key: getattr(site, key, "")
        for key in (
            "company_name",
            "legal_name",
            "email",
            "inn",
            "registration_number",
            "address",
            "return_address",
        )
    }
    values["phone"] = (site.phone_label or site.phone) if site else ""
    # Retain the old placeholder for owner-authored static-delivery copy only.
    values["delivery_price"] = (
        "рассчитывается при выборе пункта выдачи"
        if method and method.type == "cdek_pvz"
        else format(method.price, ".2f").replace(".00", "").replace(".", ",")
        if method
        else "не определена"
    )
    values["legal_name"] = values["legal_name"] or "сведения о продавце уточняются"
    values["main_url"] = settings.MAIN_ORIGIN
    values["shop_url"] = settings.SHOP_ORIGIN
    return values


def customer_sales_available(store):
    """Order access follows checkout readiness, including explicitly enabled trial payments."""
    return bool(
        store
        and store.checkout_enabled
        and settings.CHECKOUT_ENABLED
        and store.terms_text.strip()
        and store.privacy_text.strip()
        and DeliveryMethod.objects.filter(active=True).exists()
    )


def render_customer_text(text, values=None):
    values = text_values() if values is None else values
    return re.sub(r"\{([a-z_]+)\}", lambda match: str(values.get(match[1], match[0])), text or "")


def text_blocks(text):
    blocks = []
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        if paragraph:
            if paragraph.startswith("## "):
                heading, _, body = paragraph.partition("\n")
                blocks.append({"kind": "heading", "text": heading[3:].strip()})
                if body.strip():
                    blocks.append({"kind": "paragraph", "text": body.strip()})
            else:
                blocks.append({"kind": "paragraph", "text": paragraph})
    return blocks


def seller_details(site):
    if not site:
        return []
    fields = [
        ("Продавец", "legal_name"),
        ("ИНН", "inn"),
        ("ОГРНИП" if site.seller_type == "ip" else "ОГРН", "registration_number"),
        ("Регистрирующий орган", "registration_authority"),
        ("КПП", "kpp"),
        ("Адрес продавца", "address"),
        ("Почтовый адрес", "postal_address"),
        ("Адрес возврата", "return_address"),
        ("Банк", "bank_name"),
        ("БИК", "bank_bik"),
        ("Расчётный счёт", "bank_account"),
        ("Корреспондентский счёт", "correspondent_account"),
    ]
    return [(label, getattr(site, field)) for label, field in fields if getattr(site, field)]
