"""Frequency counts for sampled computed typography, not font licensing."""
from collections import Counter

PROPERTIES = ("font-family", "font-size", "font-weight", "font-style", "line-height", "letter-spacing")


def frequency(elements, properties, limit=20):
    result = {}
    for prop in properties:
        counter = Counter(row.get("style", {}).get(prop) for row in elements)
        counter.pop(None, None)
        counter.pop("", None)
        result[prop] = [{"value": value, "count": count} for value, count in sorted(
            counter.items(), key=lambda item: (-item[1], item[0]))[:limit]]
    return result


def typography(elements):
    return frequency(elements, PROPERTIES)
