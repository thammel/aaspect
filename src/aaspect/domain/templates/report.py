"""Template conformance results as report tables."""

from collections import Counter
from collections.abc import Iterable

from aaspect.domain.blocks import Table
from aaspect.domain.templates.catalogue import Catalogue
from aaspect.domain.templates.check import DeviationKind
from aaspect.domain.templates.tally import ConformanceTally, TemplateCounts, short

# A corpus can hold thousands of semanticIds without a template; the tail says little.
_MAX_UNCOVERED_ROWS = 100
_KIND_LABELS = {
    DeviationKind.MISSING: "Missing",
    DeviationKind.CARDINALITY: "Cardinality",
    DeviationKind.MODEL_TYPE: "Model type",
    DeviationKind.VALUE_TYPE: "Value type",
    DeviationKind.SEMANTIC_ID_VERSION: "semanticId version",
    DeviationKind.ID_SHORT: "idShort",
    DeviationKind.UNEXPECTED: "Not in template",
}


def summary_table(submodels: int, tally: ConformanceTally, unchecked: int) -> Table:
    """`unchecked` counts submodels with a template that were not checked: too large, or
    left out by the time limit."""
    with_template = tally.checked + unchecked
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
                tally.checked,
                tally.conformant,
                tally.checked - tally.conformant,
                submodels - with_template,
            ),
        ),
    )


def catalogue_table(catalogue: Catalogue) -> Table:
    return Table(
        "Templates",
        ("Template files", "Templates used", "Same id as a preferred one", "Unusable"),
        ((catalogue.files, len(catalogue), catalogue.duplicates, len(catalogue.problems)),),
    )


def template_table(tally: ConformanceTally) -> Table:
    return Table(
        "Conformance per template",
        ("Template", "Source", "Submodels", "Conformant", "Errors", "Notes"),
        tuple(
            (short(name), tier, c.submodels, c.conformant, c.errors, c.notes)
            for (name, tier), c in _ordered(tally)
        ),
    )


def deviation_table(tally: ConformanceTally) -> Table:
    """Places per template and kind of deviation; kinds no template shows are left out."""
    ordered = [(name, c) for (name, _), c in _ordered(tally) if c.by_kind]
    kinds = [kind for kind in _KIND_LABELS if any(c.by_kind[kind] for _, c in ordered)]
    return Table(
        "Deviations per template and kind, counted per place",
        ("Template", *(_KIND_LABELS[kind] for kind in kinds)),
        tuple((short(name), *(c.by_kind[kind] for kind in kinds)) for name, c in ordered),
    )


def uncovered_table(semantic_ids: Iterable[str | None]) -> Table:
    """semanticIds of submodels no template names: what the check did not cover at all."""
    counts = Counter(
        short(semantic_id) if semantic_id else "(no semanticId)" for semantic_id in semantic_ids
    )
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    shown = ranked[:_MAX_UNCOVERED_ROWS]
    return Table(
        f"Submodels without a template, by semanticId ({len(shown)} of {len(ranked)})",
        ("semanticId", "Submodels"),
        tuple(shown),
    )


def _ordered(tally: ConformanceTally) -> list[tuple[tuple[str, str], TemplateCounts]]:
    return sorted(
        tally.per_template.items(),
        key=lambda item: (-item[1].errors, -item[1].submodels, item[0]),
    )
