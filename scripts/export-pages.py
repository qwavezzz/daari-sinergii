"""Render a read-only Pages preview from an isolated, seeded in-memory database."""

import html
import json
import os
import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urljoin, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_dev"
# A preview never inherits a production database, payment flag or storage path.
os.environ.pop("DATABASE_URL", None)
os.environ["CHECKOUT_ENABLED"] = "false"
os.environ["YOOKASSA_ENABLED"] = "false"

import django
from django.conf import settings

settings.DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
settings.VITE_MANIFEST_PATH = ROOT / "var/pages-dist/.vite/manifest.json"
settings.MAIN_HOST = "pages-main.local"
settings.SHOP_HOST = "pages-shop.local"
settings.MAIN_ORIGIN = "http://pages-main.local"
settings.SHOP_ORIGIN = "http://pages-shop.local"
settings.SITE_INDEXING_ENABLED = False
settings.ALLOWED_HOSTS = [settings.MAIN_HOST, settings.SHOP_HOST]
django.setup()

from django.core.management import call_command
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import Client
from django.urls import set_urlconf
from catalog.models import Category, Product
from content.models import Collection, Document

BASE = os.environ.get("PAGES_BASE_PATH", "/daari-sinergii/")
if not re.fullmatch(r"/(?:[a-zA-Z0-9_-]+/)*", BASE):
    raise ValueError("Invalid PAGES_BASE_PATH")
PUBLIC_ORIGIN = os.environ.get("PAGES_ORIGIN", "https://qwavezzz.github.io").rstrip("/")
OUTPUT = (ROOT / "var/pages-site").resolve()
assert OUTPUT.is_relative_to((ROOT / "var").resolve()) and OUTPUT.name == "pages-site"
if OUTPUT.exists():
    shutil.rmtree(OUTPUT)
OUTPUT.mkdir(parents=True)


def route(shop, path, query=""):
    values = parse_qs(query)
    if path.startswith("/static/"):
        return BASE + path.lstrip("/")
    if path.startswith("/product-images/"):
        return BASE + "shop" + path.rstrip("/")
    if path.startswith("/documents/"):
        return BASE + "documents/" + path.rstrip("/").split("/")[-1].removesuffix(".pdf") + ".pdf"
    if shop and path == "/":
        suffix = "shop/"
        if values.get("category"):
            suffix += "category/" + values["category"][0] + "/"
        if values.get("page", ["1"])[0] != "1":
            suffix += "page/" + values["page"][0] + "/"
        return BASE + suffix
    if not shop and path == "/materials/" and values.get("direction", ["all"])[0] != "all":
        return BASE + "materials/filter/" + values["direction"][0] + "/"
    return BASE + ("shop/" if shop else "") + path.lstrip("/")


class PreviewHTML(HTMLParser):
    def __init__(self, shop, source_path, product_json):
        super().__init__(convert_charrefs=False)
        self.shop = shop
        self.source_path = source_path
        self.origin = settings.SHOP_ORIGIN if shop else settings.MAIN_ORIGIN
        self.product_json = product_json
        self.parts = []
        self.demo_form = False

    def url(self, value):
        if not value or value.startswith(("#", "mailto:", "tel:", "data:", "javascript:")):
            return value
        parsed = urlsplit(urljoin(self.origin + self.source_path, value))
        if parsed.hostname not in {settings.MAIN_HOST, settings.SHOP_HOST}:
            return value
        result = route(parsed.hostname == settings.SHOP_HOST, parsed.path, parsed.query)
        return result + ("#" + parsed.fragment if parsed.fragment else "")

    def handle_decl(self, decl):
        self.parts.append("<!" + decl + ">")

    def handle_comment(self, data):
        self.parts.append("<!--" + data + "-->")

    def handle_data(self, data):
        self.parts.append(data)

    def handle_entityref(self, name):
        self.parts.append("&" + name + ";")

    def handle_charref(self, name):
        self.parts.append("&#" + name + ";")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_starttag(self, tag, attrs):
        original = dict(attrs)
        if tag == "input" and original.get("name") == "csrfmiddlewaretoken":
            return
        if tag == "form":
            self.demo_form = "data-cart-add" in original
            if original.get("method", "get").lower() == "post" and not self.demo_form:
                raise ValueError("Unexpected writable form in static preview")
        output = []
        for name, value in attrs:
            if name.startswith("hx-"):
                continue
            if self.demo_form and tag == "form" and name in {"action", "method"}:
                continue
            if value is not None:
                if name in {"href", "src", "poster", "data-src", "action", "data-canonical"}:
                    value = self.url(value)
                    if name == "data-canonical" or (tag == "link" and original.get("rel") == "canonical"):
                        value = PUBLIC_ORIGIN + value
                elif name == "srcset":
                    value = ", ".join(
                        " ".join([self.url(entry.split()[0]), *entry.split()[1:]])
                        for entry in value.split(",")
                    )
                elif name == "style":
                    value = value.replace("/static/", BASE + "static/")
                elif name == "content" and original.get("property") in {"og:url", "og:image"}:
                    value = PUBLIC_ORIGIN + self.url(value)
                elif name == "data-noindex":
                    value = "true"
            output.append((name, value))
        if tag == "html":
            output.extend([("data-static-demo", "true"), ("data-demo-base", BASE)])
        if tag == "form" and self.demo_form:
            match = re.search(r"/cart/add/(\d+)/", original["action"])
            if not match:
                raise ValueError("Unknown add-to-cart form")
            output.extend([("data-demo-add", match[1]), ("action", "#")])
        if tag == "button" and self.demo_form:
            output.append(("disabled", None))
        attributes = "".join(
            " " + name + ('="' + html.escape(value, quote=True) + '"' if value is not None else "")
            for name, value in output
        )
        self.parts.append("<" + tag + attributes + ">")
        if tag == "head":
            self.parts.append('<meta name="robots" content="noindex, nofollow">')

    def handle_endtag(self, tag):
        if tag == "form" and self.demo_form:
            self.parts.append(
                "<p data-demo-js-required>Для пробной корзины включите JavaScript. Заказы в демоверсии не принимаются.</p>"
            )
            self.demo_form = False
        if tag == "body" and self.shop:
            self.parts.append(
                '<script type="application/json" id="demo-products">' + self.product_json + "</script>"
            )
        self.parts.append("</" + tag + ">")


def write_page(url, body):
    relative = url.removeprefix(BASE)
    destination = OUTPUT / relative / "index.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(body, encoding="utf-8")


with TemporaryDirectory(prefix="dari-pages-") as scratch:
    settings.PRIVATE_MEDIA_ROOT = Path(scratch) / "private"
    settings.MEDIA_ROOT = Path(scratch) / "media"
    call_command("migrate", verbosity=0)
    call_command("import_legacy_content", verbosity=0)
    call_command("apply_seo_content", apply=True, verbosity=0)
    call_command("seed_demo_catalog", verbosity=0)

    products = list(Product.objects.filter(status="published").prefetch_related("images"))
    product_json = (
        json.dumps(
            [
                {
                    "id": product.pk,
                    "name": product.name,
                    "sku": product.sku,
                    "price": int(product.price * 100),
                    "stock": product.available_quantity,
                    "url": route(True, product.get_absolute_url()),
                    "image": route(True, product.image_url),
                }
                for product in products
            ],
            ensure_ascii=False,
        )
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    pages = [(False, "/"), (False, "/materials/"), (True, "/"), (True, "/?page=2")]
    for collection in Collection.objects.published():
        pages.extend(
            [(False, collection.get_absolute_url()), (False, f"/materials/?direction={collection.slug}")]
        )
    for category in Category.objects.filter(active=True):
        pages.append((True, f"/?category={category.slug}"))
    pages.extend((True, product.get_absolute_url()) for product in products)
    pages.extend(
        (True, path)
        for path in ["/cart/", "/checkout/", "/delivery-and-payment/", "/legal/terms/", "/legal/privacy/"]
    )
    client = Client()
    for shop, source_path in pages:
        response = client.get(source_path, HTTP_HOST=settings.SHOP_HOST if shop else settings.MAIN_HOST)
        if shop and source_path == "/checkout/" and response.status_code == 302:
            set_urlconf("config.shop_urls")
            response = HttpResponse(
                render_to_string(
                    "shop/checkout.html",
                    {
                        "checkout_enabled": False,
                        "page_title": "Демонстрация — оформление недоступно",
                        "canonical_url": settings.SHOP_ORIGIN + source_path,
                    },
                    request=response.wsgi_request,
                )
            )
            set_urlconf(None)
        if response.status_code != 200:
            raise ValueError(f"Cannot export {source_path}: {response.status_code}")
        parser = PreviewHTML(shop, source_path, product_json)
        parser.feed(response.content.decode())
        parsed = urlsplit(source_path)
        write_page(route(shop, parsed.path, parsed.query), "".join(parser.parts))

    for product in products:
        for picture in product.images.all():
            destination = OUTPUT / route(True, picture.image.url).removeprefix(BASE)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with picture.image.open("rb") as source:
                destination.write_bytes(source.read())
    for document in Document.objects.published():
        destination = OUTPUT / "documents" / f"{document.slug}.pdf"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with document.file.open("rb") as source:
            destination.write_bytes(source.read())

    static = OUTPUT / "static"
    static.mkdir(exist_ok=True)
    for entry in (ROOT / "public").iterdir():
        if entry.name in {"documents", "CNAME"}:
            continue
        if entry.is_dir():
            shutil.copytree(entry, static / entry.name, ignore=shutil.ignore_patterns("source"))
        else:
            shutil.copy2(entry, static / entry.name)
    shutil.copytree(ROOT / "var/pages-dist", static / "dist")

(OUTPUT / ".nojekyll").write_text("", encoding="utf-8")
(OUTPUT / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
(OUTPUT / "build-info.json").write_text(
    json.dumps({"revision": os.environ.get("GITHUB_SHA", "local"), "mode": "static-demo", "products": 16}),
    encoding="utf-8",
)
(OUTPUT / "404.html").write_text(
    '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta name="robots" content="noindex"><title>Страница не найдена</title>'
    f'<body><main><h1>Страница не найдена</h1><p><a href="{BASE}">На главную</a> · <a href="{BASE}shop/">Демонстрационный каталог</a></p></main></body></html>',
    encoding="utf-8",
)
size = sum(path.stat().st_size for path in OUTPUT.rglob("*") if path.is_file())
print(
    f"Pages preview: {len(pages)} pages, {len(products)} products, {size / 1_000_000:.2f} MB; output: {OUTPUT}"
)
