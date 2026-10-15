"""Constraint violations grouped into report findings, one per rule."""

from collections.abc import Iterable, Mapping

from aaspect.domain.blocks import Finding, Location, Severity
from aaspect.domain.constraints.rules import rule_text
from aaspect.domain.constraints.violations import Place, RuleResult
from aaspect.domain.id_collisions import Occurrence

# Ids and idShorts come from the files and can be megabytes long.
_MAX_TEXT = 256
# The web page shows a few; the JSON gets these. More only make the report heavier.
_MAX_LOCATIONS = 1_000


def violation_findings(
    rules: Iterable[RuleResult], occurrences: Mapping[tuple[str, int], Occurrence]
) -> tuple[Finding, ...]:
    """One finding per rule with violations. An object found in many files is listed once,
    with the first of its files; `occurrences` is keyed by original id and collision
    index."""
    return tuple(_finding(rule, occurrences) for rule in rules if rule.total)


def _finding(rule: RuleResult, occurrences: Mapping[tuple[str, int], Occurrence]) -> Finding:
    places = dict.fromkeys(place for violation in rule.violations for place in violation.places)
    locations = tuple(dict.fromkeys(_location(place, occurrences) for place in places))
    message = f"{rule_text(rule.rule_id)}. {_count(rule.total, 'violation')}."
    objects = {(place.identifiable_id, place.collision_index) for place in places}
    files = sum(occurrences[key].documents for key in objects if key in occurrences)
    if files > len(objects):
        message += (
            f" Found in {_count(len(objects), 'object')} with {files:,} file occurrences;"
            " each location names the first file."
        )
    unplaced = sum(1 for violation in rule.violations if not violation.places)
    if unplaced:
        message += f" {_count(unplaced, 'violation')} without a location found in the graph."
    if any(violation.more_places for violation in rule.violations):
        message += " Some are shared by more objects than listed."
    if len(locations) > _MAX_LOCATIONS or len(rule.violations) < rule.total:
        message += " Not every location is listed."
    return Finding(rule.rule_id, Severity.ERROR, message, locations[:_MAX_LOCATIONS])


def _location(place: Place, occurrences: Mapping[tuple[str, int], Occurrence]) -> Location:
    occurrence = occurrences.get((place.identifiable_id, place.collision_index))
    return Location(
        file=occurrence.first_document if occurrence else None,
        identifiable_id=_shortened(place.identifiable_id),
        element_path=_shortened(place.element_path) or None,
    )


def _shortened(text: str) -> str:
    return text if len(text) <= _MAX_TEXT else text[: _MAX_TEXT - 1] + "…"


def _count(number: int, noun: str) -> str:
    return f"{number:,} {noun}" if number == 1 else f"{number:,} {noun}s"
