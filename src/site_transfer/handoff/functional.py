"""Offline functional observations, not inferred business requirements."""
from collections import defaultdict
from dataclasses import dataclass

from .models import EvidenceBundle, EvidenceKind, EvidenceRef, JsonValue
from .pages import PREFIX, obj, rows, ref, stable_id, quality
from .structure import StructureIntelligence


@dataclass(frozen=True, slots=True)
class FunctionalObservation:
    id: str
    page_id: str
    viewport: str
    action: str
    selector: str | None
    component_id: str | None
    association: str
    status: str
    capture_status: str
    quality: str
    expectation: str | None
    expectation_verified: bool | None
    before: JsonValue
    after: JsonValue
    evidence: EvidenceRef
    screenshot: EvidenceRef | None
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FunctionalMap:
    observations: tuple[FunctionalObservation, ...]
    limitations: tuple[str, ...]


def component_index(structure):
    index = defaultdict(list)
    for c in structure.components.components:
        index[(c.url, c.viewport, c.selector)].append(c.id)
    return index


def component_candidate(index, url, viewport, selector):
    if not isinstance(selector, str):
        return None
    ids = index.get((url, viewport, selector), ())
    return ids[0] if len(ids) == 1 else None


def build_functional_map(bundle: EvidenceBundle, structure: StructureIntelligence) -> FunctionalMap:
    if bundle.run_id != structure.run_id:
        raise ValueError("Structure belongs to a different run")
    routes = {p.page.url for p in structure.pages}
    index = component_index(structure)
    result = []
    limits = {"no_backend_or_submission_verification",
              "visibility_expectation_does_not_prove_transition",
              "explicit_scenarios_run_in_separate_contexts"}
    path = "interaction-manifest.json"
    document = obj(bundle.documents.get(PREFIX + path))
    if not document:
        limits.add("explicit_interaction_evidence_unavailable")
    for i, raw in enumerate(rows(document.get("states"))):
        state = obj(raw)
        url, viewport = state.get("url"), state.get("viewport")
        if not isinstance(url, str) or url not in routes or not isinstance(viewport, str):
            limits.add("unattributed_interaction")
            continue
        action = state.get("action")
        if action not in ("click", "focus", "hover", "scroll"):
            limits.add("unsupported_interaction_action")
            continue
        selector = state.get("selector")
        selector = selector if isinstance(selector, str) else None
        component = component_candidate(index, url, viewport, selector)
        capture = state.get("status", "unknown")
        capture = capture if isinstance(capture, str) else "unknown"
        q = quality(state)
        expected = state.get("expect_visible")
        expected = expected if isinstance(expected, str) and expected else None
        verified = state.get("expectation_verified")
        verified = verified if type(verified) is bool else None
        screenshot = ref(bundle, state.get("path"), kind=EvidenceKind.INTERACTION_SCREENSHOT) if capture == "captured" else None
        notes = []
        if capture != "captured":
            status = "unverified"
            notes.append("scenario_not_captured")
        elif screenshot is None or q == "invalid" or verified is False:
            status = "partial"
            notes.append("inconsistent_or_incomplete_capture")
        elif q != "valid":
            status = "partial"
            notes.append("capture_quality_not_validated")
        elif expected and verified is True:
            status = "confirmed"
            notes.append("post_action_visibility_only")
        else:
            status = "observed"
            notes.append("no_verified_explicit_expectation")
        result.append(FunctionalObservation(
            stable_id("FUNC", bundle.run_id, path, i), stable_id("PAGE", bundle.run_id, url),
            viewport, action, selector, component, "candidate" if component else "unmatched",
            status, capture, q, expected, verified, state.get("before"), state.get("after"),
            ref(bundle, path, f"/states/{i}"), screenshot, tuple(notes),
        ))
    return FunctionalMap(tuple(result), tuple(sorted(limits)))
