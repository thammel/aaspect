"""Template conformance results as report tables and findings."""

import dataclasses
import re
from collections import Counter
from collections.abc import Iterable, Sequence

from aaspect.domain.analytics.tables import text
from aaspect.domain.blocks import Block, Finding, Location, Severity, Table
from aaspect.domain.templates.check import SEVERITY, Deviation, DeviationKind
from aaspect.domain.templates.instances import CheckedSubmodel

# Values come from the files and can be megabytes long.
_MAX_TEXT = 256
# Locations per finding, and findings per section: more only make the report heavier.
_MAX_LOCATIONS = 1_000
_MAX_FINDINGS = 500
_LIST_POSITION = re.compile(r"\[\d+\]")

_DESCRIPTIONS = {
    DeviationKind.MISSING: "mandatory element missing",
    DeviationKind.CARDINALITY: "element occurs a number of times the template does not allow",
    DeviationKind.MODEL_TYPE: "element of another type than in the template",
    DeviationKind.VALUE_TYPE: "value type differs from the template",
    DeviationKind.SEMANTIC_ID_VERSION: "semanticId in another version than in the template",
    DeviationKind.ID_SHORT: "idShort differs from the template",
    DeviationKind.UNEXPECTED: "element the template does not define",
}

type _Group = tuple[DeviationKind, str, str, str, str]


def summary_table(submodels: int, checked: Sequence[CheckedSubmodel], unchecked: int) -> Table:
    """`unchecked` counts submodels with a template that the time limit left out."""
    conformant = sum(1 for result in checked if not _errors(result.deviations))
    with_template = len(checked) + unchecked
    return Table(
        "Template conformance, counted as distinct contents",
        (
            "Submodels",
            "With a template",
            "Checked",
            "Conformant",
            "With errors",
            "Without a template",
        ),
        (
            (
                submodels,
                with_template,
                len(checked),
                conformant,
                len(checked) - conformant,
                submodels - with_template,
            ),
        ),
    )


def catalogue_table(files: int, used: int, duplicates: int, unusable: int) -> Table:
    return Table(
        "Templates",
        ("Template files", "Templates used", "Same id as a preferred one", "Unusable"),
        ((files, used, duplicates, unusable),),
    )


def template_table(checked: Iterable[CheckedSubmodel]) -> Table:
    rows: dict[tuple[str, str], list[int]] = {}
    for result in checked:
        row = rows.setdefault((result.template.name, result.template.tier.value), [0, 0, 0, 0])
        errors = _errors(result.deviations)
        row[0] += 1
        row[1] += not errors
        row[2] += errors
        row[3] += len(result.deviations) - errors
    ordered = sorted(rows.items(), key=lambda item: (-item[1][2], -item[1][0], item[0]))
    return Table(
        "Conformance per template",
        ("Template", "Source", "Submodels", "Conformant", "Errors", "Notes"),
        tuple((text(name), tier, *counts) for (name, tier), counts in ordered),
    )


def deviation_findings(checked: Iterable[CheckedSubmodel]) -> tuple[Block, ...]:
    """One finding per kind of deviation, template, element path, expectation and actual
    value, where the path leaves out list positions; errors first, then the most
    frequent."""
    groups: dict[_Group, list[Location]] = {}
    for result in checked:
        for deviation in result.deviations:
            key = (
                deviation.kind,
                result.template.name,
                _LIST_POSITION.sub("[]", deviation.path),
                deviation.expected,
                deviation.actual,
            )
            place = dataclasses.replace(result.location, element_path=_short(deviation.path))
            groups.setdefault(key, []).append(place)
    ordered = sorted(
        groups.items(), key=lambda item: (SEVERITY[item[0][0]] != Severity.ERROR, -len(item[1]))
    )
    findings: list[Block] = [_finding(key, places) for key, places in ordered[:_MAX_FINDINGS]]
    if len(ordered) > _MAX_FINDINGS:
        left = Counter(SEVERITY[key[0]].value for key, _ in ordered[_MAX_FINDINGS:])
        findings.append(
            Finding(
                "template-more",
                Severity.INFO,
                f"{len(ordered) - _MAX_FINDINGS:,} further kinds of deviation not listed"
                f" ({left['error']:,} errors, {left['info']:,} notes).",
            )
        )
    return tuple(findings)


def _finding(key: _Group, places: list[Location]) -> Finding:
    kind, template, path, expected, actual = key
    submodels = len({(place.file, place.identifiable_id) for place in places})
    message = (
        f"{_short(template)}: {_DESCRIPTIONS[kind]} at {_short(path)}"
        f" (template: {_short(expected)}; found: {_short(actual)})."
        f" {_count(submodels, 'submodel')}"
    )
    message += f", {_count(len(places), 'place')}." if len(places) > submodels else "."
    if len(places) > _MAX_LOCATIONS:
        message += " Not every location is listed."
    return Finding(kind.value, SEVERITY[kind], message, tuple(places[:_MAX_LOCATIONS]))


def _count(number: int, noun: str) -> str:
    return f"{number:,} {noun}" if number == 1 else f"{number:,} {noun}s"


def _errors(deviations: Iterable[Deviation]) -> int:
    return sum(1 for deviation in deviations if SEVERITY[deviation.kind] is Severity.ERROR)


def _short(value: str) -> str:
    shown = text(value)
    return shown if len(shown) <= _MAX_TEXT else shown[: _MAX_TEXT - 1] + "…"
