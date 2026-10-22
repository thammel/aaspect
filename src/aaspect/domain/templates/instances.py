"""Submodels of the corpus as the graph hands them to template conformance."""

from dataclasses import dataclass

from aaspect.domain.blocks import Location
from aaspect.domain.templates.catalogue import Template
from aaspect.domain.templates.check import Deviation
from aaspect.domain.templates.elements import Element


@dataclass(frozen=True, slots=True)
class SubmodelRef:
    """A stored submodel: `node` names it in the graph, `occurrence` is its position in
    the import's occurrences, None if it has none."""

    node: str
    occurrence: int | None
    semantic_id: str | None


@dataclass(frozen=True, slots=True)
class InstanceSubmodel:
    node: str
    elements: tuple[Element, ...]


@dataclass(frozen=True, slots=True)
class CheckedSubmodel:
    """`location` names the submodel; each deviation adds its element path to it."""

    template: Template
    location: Location
    deviations: tuple[Deviation, ...]
