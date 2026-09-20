"""Read-only public HTTP/SEO inventory; no login, POST, cookies or SMTP delivery."""

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

ORIGINS = ("https://dari-sinergii.ru", "https://shop.dari-sinergii.ru")


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
        self.headings = []
        self.heading = None
        self.meta = {}
        self.canonical = []
        self.links = set()
        self.images = 0
        self.missing_alt = 0
        self.json_ld = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag in {"h1", "h2"}:
            self.heading = [tag, ""]
            self.headings.append(self.heading)
        if tag == "meta":
            self.meta[attrs.get("name", attrs.get("property", ""))] = attrs.get("content", "")
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical.append(attrs.get("href", ""))
        if tag == "a" and attrs.get("href"):
            self.links.add(attrs["href"])
        if tag == "img":
            self.images += 1
            self.missing_alt += "alt" not in attrs
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.json_ld += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in {"h1", "h2"}:
            self.heading = None

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.heading is not None:
            self.heading[1] += data


def fetch(url):
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": "DariReadinessAudit/1.0"})
    try:
        response = urllib.request.urlopen(request, timeout=20)
    except urllib.error.HTTPError as exc:
        response = exc
    except (OSError, urllib.error.URLError) as exc:
        return {"url": url, "error": type(exc).__name__}, ""
    with response:
        body = response.read(3 * 1024 * 1024).decode("utf-8", errors="replace")
        headers = {
            key.lower(): value for key, value in response.headers.items() if key.lower() != "set-cookie"
        }
        return {
            "url": url,
            "final_url": response.url,
            "status": response.status,
            "seconds": round(time.monotonic() - started, 3),
            "headers": headers,
        }, body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/readiness/public-http.json"))
    args = parser.parse_args()
    urls = []
    for origin in ORIGINS:
        urls.extend(origin + path for path in ("/", "/robots.txt", "/sitemap.xml", "/health/"))
        urls.append(origin.replace("https:", "http:") + "/")
    urls.extend(
        [
            "https://www.dari-sinergii.ru/",
            ORIGINS[1] + "/?page=2",
            ORIGINS[1] + "/admin/login/",
            ORIGINS[1] + "/legal/privacy/",
            ORIGINS[1] + "/legal/terms/",
            ORIGINS[0] + "/this-page-does-not-exist-audit/",
        ]
    )
    records = []
    visited = set()
    for url in urls:
        if url in visited or len(visited) >= 80:
            continue
        visited.add(url)
        record, body = fetch(url)
        if "text/html" in record.get("headers", {}).get("content-type", ""):
            page = Page()
            page.feed(body)
            record["seo"] = {
                "title": page.title.strip(),
                "headings": page.headings,
                "meta": page.meta,
                "canonical": page.canonical,
                "images": page.images,
                "images_without_alt": page.missing_alt,
                "json_ld_in_source": page.json_ld,
            }
            for link in sorted(page.links):
                target = urljoin(url, link).split("#")[0]
                parsed = urlsplit(target)
                if (
                    parsed.scheme == "https"
                    and parsed.netloc in {"dari-sinergii.ru", "shop.dari-sinergii.ru"}
                    and parsed.path.startswith(("/materials/", "/documents/", "/products/"))
                ):
                    urls.append(target)
        if url.endswith("robots.txt"):
            record["body"] = body
        if url.endswith("sitemap.xml") and record.get("status") == 200:
            try:
                record["locations"] = [
                    loc.text
                    for loc in ElementTree.fromstring(body).iter(
                        "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
                    )
                ]
                urls.extend(
                    loc
                    for loc in record["locations"]
                    if any(loc.startswith(origin + "/") for origin in ORIGINS)
                )
            except ElementTree.ParseError:
                record["xml_error"] = True
        records.append(record)
        print(record.get("status", "ERROR"), url, flush=True)
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"checked_at": datetime.now(timezone.utc).isoformat(), "responses": records},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
