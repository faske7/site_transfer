"""Sampled design inventory; no inferred brand palette or authored CSS tokens."""
from collections import defaultdict
from dataclasses import dataclass

from .components import ComponentMap
from .models import EvidenceBundle, EvidenceKind, EvidenceRef
from .pages import PREFIX, obj, rows, ref

_CATEGORIES = {
    "typography": ("font-family", "font-size", "font-weight", "font-style",
                   "line-height", "letter-spacing", "text-align", "text-transform"),
    "colors": ("color", "background-color", "border-top-color", "border-right-color",
               "border-bottom-color", "border-left-color"),
    "spacing": ("gap", "row-gap", "column-gap", "padding-top", "padding-right",
                "padding-bottom", "padding-left", "margin-top", "margin-right",
                "margin-bottom", "margin-left"),
    "layout": ("display", "position", "width", "height", "min-width", "max-width",
               "min-height", "max-height", "flex-direction", "flex-wrap",
               "align-items", "justify-content", "grid-template-columns",
               "grid-template-rows", "box-sizing", "z-index", "overflow-x", "overflow-y"),
    "borders": ("border-radius", "border-top-width", "border-right-width",
                "border-bottom-width", "border-left-width", "border-top-style",
                "box-shadow"),
    "media": ("aspect-ratio", "object-fit", "object-position"),
}
_PROPERTY_CATEGORY = {p: category for category, props in _CATEGORIES.items() for p in props}


@dataclass(frozen=True, slots=True)
class DesignUse:
    component_id: str
    evidence: EvidenceRef


@dataclass(frozen=True, slots=True)
class DesignValue:
    category: str
    property: str
    value: str
    count: int
    uses: tuple[DesignUse, ...]


@dataclass(frozen=True, slots=True)
class CapturedToken:
    category: str
    property: str
    value: str
    count: int
    evidence: EvidenceRef


@dataclass(frozen=True, slots=True)
class DesignSystem:
    component_values: tuple[DesignValue, ...]
    captured_tokens: tuple[CapturedToken, ...]
    limitations: tuple[str, ...]


def _escape_pointer(value):
    return value.replace("~", "~0").replace("/", "~1")


def build_design_system(bundle: EvidenceBundle, component_map: ComponentMap) -> DesignSystem:
    """Preserve exact CSS and source pointers; counts are sample occurrences.

    The captured aggregate is kept separate from component observations:
    the former includes other sampled elements and may have been truncated.
    """
    grouped = defaultdict(list)
    for component in component_map.components:
        for prop, value in component.styles:
            category = _PROPERTY_CATEGORY.get(prop)
            if category is None:
                continue
            pointer = component.measurement.json_pointer + "/style/" + _escape_pointer(prop)
            grouped[(category, prop, value)].append(DesignUse(
                component.id, EvidenceRef(component.measurement.evidence_id, pointer)))
    values = tuple(
        DesignValue(category, prop, value, len(uses), tuple(uses))
        for (category, prop, value), uses in sorted(grouped.items())
    )
    tokens = []
    limits = {"sampled_computed_css_only", "counts_are_not_design_token_semantics",
              "captured_aggregate_and_component_counts_not_comparable"}
    path = "design-tokens.json"
    doc = obj(bundle.documents.get(PREFIX + path))
    if not doc:
        limits.add("aggregate_tokens_unavailable")
    else:
        for category, properties in sorted(obj(doc.get("tokens")).items()):
            for prop, observations in sorted(obj(properties).items()):
                for i, raw in enumerate(rows(observations)):
                    row = obj(raw)
                    value, count = row.get("value"), row.get("count")
                    if not isinstance(value, str) or type(count) is not int or count < 1:
                        limits.add("unsupported_token_record")
                        continue
                    pointer = "/tokens/" + _escape_pointer(category) + "/" + _escape_pointer(prop) + "/" + str(i)
                    tokens.append(CapturedToken(category, prop, value, count,
                        ref(bundle, path, pointer, EvidenceKind.DESIGN_TOKENS)))
    if not values:
        limits.add("component_styles_unavailable")
    return DesignSystem(values, tuple(tokens), tuple(sorted(limits)))
