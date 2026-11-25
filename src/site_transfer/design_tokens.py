"""Aggregate bounded, observed computed values with frequency counts."""
from collections import Counter
from .typography import frequency


def summarize(snapshot):
    from .typography import typography
    from .colors import colors
    from .motion import motion
    elements = snapshot["elements"]
    return {"viewport": snapshot["viewport"], "element_count": len(elements),
            "typography": typography(elements), "colors": colors(elements),
            "spacing": frequency(elements, ("gap", "padding-top", "padding-left", "margin-top",
                                            "margin-bottom", "border-radius", "box-shadow")),
            "media_queries": snapshot["media_queries"], "motion": motion(snapshot),
            "limits": snapshot["limits"]}


def aggregate(entries):
    from .responsive import responsive
    totals = {}
    for entry in entries:
        for category in ("typography", "colors", "spacing"):
            for prop, values in entry["summary"][category].items():
                counter = totals.setdefault(category, {}).setdefault(prop, Counter())
                for value in values:
                    counter[value["value"]] += value["count"]
    return {"schema_version": 1, "basis": "Top sampled computed values per route and viewport; not exhaustive",
            "reports": len(entries),
            "tokens": {category: {prop: [{"value": value, "count": count} for value, count in
                sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:20]]
                for prop, counter in props.items()} for category, props in totals.items()},
            "responsive": responsive(entries)}
