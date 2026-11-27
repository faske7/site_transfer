"""Public composition of the offline structure intelligence stage."""
from collections import defaultdict
from dataclasses import dataclass

from .components import ComponentMap, build_component_map
from .design import DesignSystem, build_design_system
from .models import EvidenceBundle
from .pages import Page, build_page_map


@dataclass(frozen=True, slots=True)
class PageComponents:
    page: Page
    component_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StructureIntelligence:
    run_id: str
    pages: tuple[PageComponents, ...]
    components: ComponentMap
    design: DesignSystem


def build_structure(bundle: EvidenceBundle) -> StructureIntelligence:
    pages = build_page_map(bundle)
    components = build_component_map(bundle)
    ids = defaultdict(list)
    for component in components.components:
        ids[component.page_id].append(component.id)
    return StructureIntelligence(
        bundle.run_id,
        tuple(PageComponents(page, tuple(ids[page.id])) for page in pages),
        components,
        build_design_system(bundle, components),
    )
