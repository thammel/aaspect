"""Constraint violations grouped into report findings."""

from collections.abc import Iterable, Mapping

from aaspect.domain.blocks import Finding, Location, Severity
from aaspect.domain.constraints.violations import ConstraintViolation, Place
from aaspect.domain.id_collisions import Occurrence


def violation_findings(
    violations: Iterable[ConstraintViolation],
    occurrences: Mapping[tuple[str, int], Occurrence],
) -> tuple[Finding, ...]:
    """One finding per rule and message. An object found in many files is listed once,
    with the first of its files; `occurrences` is keyed by original id and collision
    index."""
    grouped: dict[tuple[str, str], list[ConstraintViolation]] = {}
    for violation in violations:
        grouped.setdefault((violation.rule_id, violation.message), []).append(violation)
    return tuple(
        _finding(rule_id, message, group, occurrences)
        for (rule_id, message), group in sorted(grouped.items())
    )


def _finding(
    rule_id: str,
    message: str,
    group: list[ConstraintViolation],
    occurrences: Mapping[tuple[str, int], Occurrence],
) -> Finding:
    places = dict.fromkeys(place for violation in group for place in violation.places)
    locations = tuple(dict.fromkeys(_location(place, occurrences) for place in places))
    objects = {(place.identifiable_id, place.collision_index) for place in places}
    files = sum(occurrences[key].documents for key in objects if key in occurrences)
    if files > len(objects):
        message += (
            f" Found in {_count(len(objects), 'object')} that occur in {files:,} files;"
            " each location names the first of those files."
        )
    if any(violation.more_places for violation in group):
        message += " Shared by more objects than listed."
    return Finding(rule_id, Severity.ERROR, message, locations)


def _location(place: Place, occurrences: Mapping[tuple[str, int], Occurrence]) -> Location:
    occurrence = occurrences.get((place.identifiable_id, place.collision_index))
    return Location(
        file=occurrence.first_document if occurrence else None,
        identifiable_id=place.identifiable_id,
        element_path=place.element_path or None,
    )


def _count(number: int, noun: str) -> str:
    return f"{number:,} {noun}" if number == 1 else f"{number:,} {noun}s"
