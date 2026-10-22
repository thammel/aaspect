"""Check every submodel of an imported corpus against the template its semanticId names."""

from collections.abc import Callable, Iterator, Sequence

from aaspect.app.import_corpus import ImportResult
from aaspect.domain.analytics.tables import text
from aaspect.domain.blocks import Block, Finding, Location, Severity
from aaspect.domain.id_collisions import Occurrence
from aaspect.domain.report import Section, SectionStatus
from aaspect.domain.templates.catalogue import Catalogue, CatalogueProblem, Template
from aaspect.domain.templates.check import deviations
from aaspect.domain.templates.instances import CheckedSubmodel, SubmodelRef
from aaspect.domain.templates.report import (
    catalogue_table,
    deviation_findings,
    summary_table,
    template_table,
)
from aaspect.ports.submodel_trees import SubmodelTrees
from aaspect.ports.template_source import TemplateSource

SECTION_KEY = "templates"
SECTION_TITLE = "Submodel template conformance"

# Submodels whose elements are fetched at once; the deadline is checked in between.
_CHUNK = 500
_MAX_TEXT = 256
_LISTED_PROBLEMS = 20


def load_catalogue(source: TemplateSource) -> Catalogue | Exception:
    """The catalogue, or why there is none: the check reports it, analytics goes without."""
    try:
        return Catalogue(source.templates())
    except Exception as error:  # Raised again by the check, which reports it.
        return error


def origin_of(catalogue: Catalogue) -> Callable[[str], str | None]:
    """The origin analytics names for a submodel semanticId a template has."""

    def origin(semantic_id: str) -> str | None:
        template = catalogue.lookup(semantic_id)
        return f"Template: {template.tier.value}" if template else None

    return origin


def check_templates(
    catalogue: Catalogue | Exception,
    graph: SubmodelTrees,
    imported: ImportResult,
    expired: Callable[[], bool] = lambda: False,
) -> Section:
    if isinstance(catalogue, Exception):
        raise catalogue
    if expired() or not imported.finished:
        return _skipped("The analysis reached its time limit.")
    if not len(catalogue):
        return _skipped("No submodel templates are available.")
    refs = graph.submodel_refs()
    matched = [(ref, template) for ref in refs if (template := catalogue.lookup(ref.semantic_id))]
    checked: list[CheckedSubmodel] = []
    for start in range(0, len(matched), _CHUNK):
        if expired():
            break
        checked.extend(_check(graph, matched[start : start + _CHUNK], imported.occurrences))
    unchecked = len(matched) - len(checked)
    blocks: list[Block] = [
        summary_table(len(refs), checked, unchecked),
        template_table(checked),
        catalogue_table(
            catalogue.files, len(catalogue), catalogue.duplicates, len(catalogue.problems)
        ),
        *deviation_findings(checked),
        *_notes(unchecked, catalogue.problems),
    ]
    return Section(SECTION_KEY, SECTION_TITLE, SectionStatus.COMPLETED, tuple(blocks))


def _check(
    graph: SubmodelTrees,
    chunk: Sequence[tuple[SubmodelRef, Template]],
    occurrences: Sequence[Occurrence],
) -> Iterator[CheckedSubmodel]:
    trees = {tree.node: tree for tree in graph.submodel_trees([ref.node for ref, _ in chunk])}
    for ref, template in chunk:
        tree = trees.get(ref.node)
        found = deviations(template.elements, tree.elements if tree else ())
        yield CheckedSubmodel(template, _location(ref, occurrences), tuple(found))


def _location(ref: SubmodelRef, occurrences: Sequence[Occurrence]) -> Location:
    """The submodel's id and the first file holding it; a submodel shared by many files is
    checked and listed once."""
    if ref.occurrence is None or not 0 <= ref.occurrence < len(occurrences):
        return Location()
    occurrence = occurrences[ref.occurrence]
    identifier = occurrence.original
    if len(identifier) > _MAX_TEXT:
        identifier = identifier[: _MAX_TEXT - 1] + "…"
    return Location(file=occurrence.first_document, identifiable_id=identifier)


def _notes(unchecked: int, problems: Sequence[CatalogueProblem]) -> Iterator[Finding]:
    if unchecked:
        yield Finding(
            "template-time-limit",
            Severity.WARNING,
            f"{unchecked:,} submodels with a template not checked: the analysis reached its"
            " time limit.",
        )
    if problems:
        listed = "; ".join(f"{text(p.name)} ({p.reason})" for p in problems[:_LISTED_PROBLEMS])
        more = (
            f"; and {len(problems) - _LISTED_PROBLEMS} more"
            if len(problems) > _LISTED_PROBLEMS
            else ""
        )
        yield Finding(
            "template-left-out",
            Severity.INFO,
            f"{len(problems)} templates left out: {listed}{more}.",
        )


def _skipped(reason: str) -> Section:
    return Section(SECTION_KEY, SECTION_TITLE, SectionStatus.SKIPPED, reason=reason)
