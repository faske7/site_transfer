"""Bounded deterministic same-origin route selection."""
from urllib.parse import urljoin, urlsplit, urlunsplit

from .browser import origin


def normalize(base, value, expected):
    try:
        parsed = urlsplit(urljoin(base, value))
        if origin(parsed.geturl()) != expected:
            return None
        if len(parsed.geturl()) > 2048:
            return None
        # Strip fragments and discovered query variants to avoid crawl explosions.
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))
    except (ValueError, TypeError):
        return None


def seed_routes(config):
    source = config["source"]["url"]
    expected = origin(source)
    limit = min(config.get("discovery", {}).get("max_pages", 30), 30)
    routes = []
    for value in [source, *config["source"].get("pages", [])]:
        url = normalize(source, value, expected)
        if url and url not in routes:
            routes.append(url)
        if len(routes) >= limit:
            break
    return routes, limit
