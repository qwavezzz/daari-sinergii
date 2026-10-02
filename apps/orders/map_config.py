"""Public map configuration; no CDEK credentials are exposed to the browser."""

import re
from urllib.parse import urlsplit

from django.conf import settings


def map_config():
    url = settings.CDEK_MAP_TILE_URL
    if not isinstance(url, str):
        return {}
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not re.fullmatch(r"[a-zA-Z0-9.-]+", parsed.hostname)
            or parsed.port is not None
            and not 1 <= parsed.port <= 65535
            or parsed.username
            or parsed.password
            or any(character in url for character in "\r\n\t ;'\"<>")
            or not all(token in url for token in ("{z}", "{x}", "{y}"))
        ):
            return {}
        origin = f"https://{parsed.netloc}"
    except (ValueError, TypeError):
        return {}
    return {"tile_url": url, "origin": origin, "attribution": settings.CDEK_MAP_ATTRIBUTION}
