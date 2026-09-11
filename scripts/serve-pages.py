"""Serve the exported artifact under the same URL prefix as GitHub Pages."""

import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

root = Path(__file__).resolve().parent.parent / "var/pages-site"
base = os.environ.get("PAGES_BASE_PATH", "/daari-sinergii/")


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if not urlsplit(path).path.startswith(base):
            return str(root / ".not-found")
        return super().translate_path("/" + path[len(base) :])


ThreadingHTTPServer(("127.0.0.1", 4173), partial(Handler, directory=str(root))).serve_forever()
