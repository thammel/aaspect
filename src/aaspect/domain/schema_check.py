"""Schema violations, and how recurring ones are grouped into findings."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from aaspect.domain.blocks import Finding, Location, Severity
from aaspect.domain.metamodel import MetamodelVersion


@dataclass(frozen=True, slots=True)
class SchemaViolation:
    keyword: str
    schema_path: str
    instance_path: str
    message: str


def group_violations(
    results: Iterable[tuple[str, MetamodelVersion, Sequence[SchemaViolation]]],
) -> tuple[Finding, ...]:
    """One finding per broken schema rule, most frequent first.

    Grouped by schema path, never by message: a message can quote the whole failing
    element, so the same rule would split into one group per occurrence.
    """
    locations: dict[tuple[MetamodelVersion, str, str], list[Location]] = {}
    first_message: dict[tuple[MetamodelVersion, str, str], str] = {}
    for file, version, violations in results:
        for violation in violations:
            key = (version, violation.keyword, violation.schema_path)
            first_message.setdefault(key, violation.message)
            locations.setdefault(key, []).append(
                Location(file=file, element_path=violation.instance_path)
            )
    ordered = sorted(locations, key=lambda key: (-len(locations[key]), key))
    return tuple(_finding(*key, first_message[key], locations[key]) for key in ordered)


def _finding(
    version: MetamodelVersion,
    keyword: str,
    schema_path: str,
    example: str,
    locations: list[Location],
) -> Finding:
    return Finding(
        rule_id=keyword,
        severity=Severity.ERROR,
        message=f"Violates {schema_path} (schema {version}): {example}",
        locations=tuple(locations),
    )
