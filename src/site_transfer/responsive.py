"""Viewport observations, without inventing inferred breakpoints."""
from collections import defaultdict


def responsive(entries):
    routes = defaultdict(list)
    for entry in entries:
        routes[entry["url"]].append({"viewport": entry["viewport"], **entry["summary"]["viewport"],
                                     "media_queries": entry["summary"]["media_queries"]})
    return [{"url": url, "observations": views} for url, views in routes.items()]
