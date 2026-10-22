"""Compare a submodel with its template: which elements are missing, too many, mistyped."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from aaspect.domain.blocks import Severity
from aaspect.domain.templates.elements import Element, id_short_matches


class DeviationKind(StrEnum):
    MISSING = "template-missing"
    CARDINALITY = "template-cardinality"
    MODEL_TYPE = "template-model-type"
    VALUE_TYPE = "template-value-type"
    SEMANTIC_ID_VERSION = "template-semantic-id-version"
    ID_SHORT = "template-id-short"
    UNEXPECTED = "template-unexpected"


SEVERITY = {
    DeviationKind.MISSING: Severity.ERROR,
    DeviationKind.CARDINALITY: Severity.ERROR,
    DeviationKind.MODEL_TYPE: Severity.ERROR,
    DeviationKind.VALUE_TYPE: Severity.ERROR,
    DeviationKind.SEMANTIC_ID_VERSION: Severity.INFO,
    DeviationKind.ID_SHORT: Severity.INFO,
    DeviationKind.UNEXPECTED: Severity.INFO,
}

_TYPED = frozenset({"Property", "Range"})
_LISTS = frozenset({"SubmodelElementList"})


@dataclass(frozen=True, slots=True)
class Deviation:
    """`path` is the idShort path inside the submodel, `expected` and `actual` what the
    template asks for and what the submodel has."""

    kind: DeviationKind
    path: str
    expected: str
    actual: str


def deviations(template: tuple[Element, ...], submodel: tuple[Element, ...]) -> list[Deviation]:
    """Elements are matched by semanticId, ignoring an IRDI's version, and by idShort
    where the template gives no semanticId or several siblings share one."""
    found: list[Deviation] = []
    _compare_level(template, submodel, "", found)
    return found


def _compare_level(
    expected: tuple[Element, ...], actual: tuple[Element, ...], path: str, found: list[Deviation]
) -> None:
    shared = _shared_keys(expected)
    by_key: dict[str, list[int]] = {}
    for index, candidate in enumerate(actual):
        if candidate.key is not None:
            by_key.setdefault(candidate.key, []).append(index)
    claimed: set[int] = set()
    for element in expected:
        matches = _matches(element, actual, by_key, element.key in shared, claimed)
        claimed.update(matches)
        here = _join(path, element.id_short)
        _check_count(element, len(matches), here, found)
        for index in matches:
            _compare_element(element, actual[index], here, found)
    for index, candidate in enumerate(actual):
        if index not in claimed:
            found.append(
                Deviation(
                    DeviationKind.UNEXPECTED,
                    _join(path, candidate.id_short),
                    "not in the template",
                    candidate.model_type or "",
                )
            )


def _matches(
    element: Element,
    actual: tuple[Element, ...],
    by_key: dict[str, list[int]],
    shared_key: bool,
    claimed: set[int],
) -> list[int]:
    """Indexes of the unclaimed elements matching `element`: by semanticId, and also by
    idShort where siblings share it; by idShort alone where it has none."""
    if element.key is None:
        pool: Iterable[int] = range(len(actual))
    else:
        pool = by_key.get(element.key, ())
        if not shared_key:
            return [index for index in pool if index not in claimed]
    return [
        index
        for index in pool
        if index not in claimed and id_short_matches(element.id_short, actual[index].id_short)
    ]


def _check_count(element: Element, count: int, path: str, found: list[Deviation]) -> None:
    bounds = element.cardinality
    if bounds is None:
        return
    allowed = f"{bounds.minimum}..{'*' if bounds.maximum is None else bounds.maximum}"
    if count == 0 and bounds.minimum > 0:
        found.append(Deviation(DeviationKind.MISSING, path, allowed, "absent"))
    elif count < bounds.minimum or (bounds.maximum is not None and count > bounds.maximum):
        found.append(Deviation(DeviationKind.CARDINALITY, path, allowed, str(count)))


def _compare_element(
    element: Element,
    candidate: Element,
    path: str,
    found: list[Deviation],
    in_list: bool = False,
) -> None:
    """`in_list` for the items of a SubmodelElementList, which carry no idShort."""
    _compare_names(element, candidate, path, found, in_list)
    if element.model_type and candidate.model_type != element.model_type:
        actual = candidate.model_type or "unknown"
        found.append(Deviation(DeviationKind.MODEL_TYPE, path, element.model_type, actual))
        return
    if (
        element.model_type in _TYPED
        and element.value_type
        and candidate.value_type
        and candidate.value_type != element.value_type
    ):
        found.append(
            Deviation(DeviationKind.VALUE_TYPE, path, element.value_type, candidate.value_type)
        )
    if element.model_type in _LISTS:
        if element.children:
            for position, item in enumerate(candidate.children):
                item_path = f"{path}[{position}]"
                _compare_element(element.children[0], item, item_path, found, in_list=True)
    elif element.children:
        _compare_level(element.children, candidate.children, path, found)


def _compare_names(
    element: Element, candidate: Element, path: str, found: list[Deviation], in_list: bool
) -> None:
    if (
        element.semantic_id is not None
        and candidate.semantic_id is not None
        and element.key == candidate.key
        and element.semantic_id.strip() != candidate.semantic_id.strip()
    ):
        found.append(
            Deviation(
                DeviationKind.SEMANTIC_ID_VERSION, path, element.semantic_id, candidate.semantic_id
            )
        )
    if (
        not in_list
        and element.id_short
        and not id_short_matches(element.id_short, candidate.id_short)
    ):
        found.append(
            Deviation(DeviationKind.ID_SHORT, path, element.id_short, candidate.id_short or "")
        )


def _shared_keys(elements: tuple[Element, ...]) -> set[str]:
    seen: set[str] = set()
    shared: set[str] = set()
    for element in elements:
        if element.key is not None:
            (shared if element.key in seen else seen).add(element.key)
    return shared


def _join(path: str, id_short: str | None) -> str:
    name = id_short if id_short is not None else "?"
    return f"{path}.{name}" if path else name
