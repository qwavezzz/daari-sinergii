"""Resolve Vite assets through its manifest without Django double hashing."""

import json
from pathlib import Path
from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join

register = template.Library()


@register.simple_tag
def vite_asset(entry):
    manifest_path = Path(
        getattr(settings, "VITE_MANIFEST_PATH", Path(settings.BASE_DIR) / "static/dist/.vite/manifest.json")
    )
    if not manifest_path.exists():
        raise template.TemplateSyntaxError("Frontend assets missing. Run npm ci && npm run build.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if entry not in manifest:
        raise template.TemplateSyntaxError(f"Vite entry missing: {entry}")
    css, imports, seen = [], [], set()

    def visit(key):
        if key in seen:
            return
        seen.add(key)
        chunk = manifest[key]
        for dependency in chunk.get("imports", []):
            visit(dependency)
        for filename in chunk.get("css", []):
            if filename not in css:
                css.append(filename)
        if key != entry:
            imports.append(chunk["file"])

    visit(entry)
    styles = format_html_join(
        "", '<link rel="stylesheet" href="{}">', ((static("dist/" + path),) for path in css)
    )
    preloads = format_html_join(
        "", '<link rel="modulepreload" href="{}">', ((static("dist/" + path),) for path in imports)
    )
    return format_html(
        '{}{}<script type="module" src="{}"></script>',
        styles,
        preloads,
        static("dist/" + manifest[entry]["file"]),
    )
