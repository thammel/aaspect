from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from aaspect.domain.blocks import Finding, Location, Severity, Table
from aaspect.domain.corpus import AasDocument, ReadFailure
from aaspect.domain.id_collisions import Collision, IdScan, Occurrence
from aaspect.domain.report import Section, SectionStatus
from aaspect.ports.environment_parser import EnvironmentParser
from aaspect.ports.graph_store import CorpusGraph

SECTION_KEY = "graph-import"
SECTION_TITLE = "Graph import"
# A corpus can hold 100,000 ids; the long tail of small repeats says little.
_MAX_REPEATED_ROWS = 100


@dataclass(frozen=True, slots=True)
class ImportResult:
    imported: int
    collisions: tuple[Collision, ...]
    not_imported: tuple[ReadFailure, ...]
    occurrences: tuple[Occurrence, ...]


def import_corpus(
    documents: Iterable[AasDocument], parser: EnvironmentParser, graph: CorpusGraph
) -> ImportResult:
    """Import every convertible document; colliding ids keep their variants apart."""
    ordered = sorted(documents, key=lambda document: document.label)
    scan = IdScan()
    importable: list[AasDocument] = []
    failures: list[ReadFailure] = []
    for document in ordered:
        try:
            scan.add(document.label, parser.parse(document))
        except (ValueError, RecursionError) as error:
            failures.append(ReadFailure(document.label, f"Not imported: {error}"))
        else:
            importable.append(document)
    plan = scan.plan()
    # Parsed a second time rather than kept: a corpus of 1 GB grows several times over
    # as Python objects, and only one document needs to be in memory at once.
    for document in importable:
        environment = parser.parse(document)
        plan.rewrite(environment)
        try:
            graph.upload(environment)
        except ValueError as error:
            failures.append(ReadFailure(document.label, f"Not imported: {error}"))
    graph.link_references()
    graph.store_occurrences(plan.occurrences)
    graph.restore_ids(plan.renames)
    failures.sort(key=lambda failure: failure.source)
    imported = len(ordered) - len(failures)
    return ImportResult(imported, plan.collisions, tuple(failures), plan.occurrences)


def import_section(result: ImportResult) -> Section:
    summary = Table(
        "Import",
        ("Documents imported", "Documents not imported", "Ids with different contents"),
        ((result.imported, len(result.not_imported), len(result.collisions)),),
    )
    not_imported = tuple(
        Finding("not-imported", Severity.ERROR, failure.reason, (Location(file=failure.source),))
        for failure in result.not_imported
    )
    collisions = tuple(
        finding for collision in result.collisions for finding in _collision_findings(collision)
    )
    blocks = (summary, _repeated(result.occurrences), *not_imported, *collisions)
    return Section(SECTION_KEY, SECTION_TITLE, SectionStatus.COMPLETED, blocks)


def _repeated(occurrences: tuple[Occurrence, ...]) -> Table:
    repeated = sorted(
        (o for o in occurrences if o.documents > 1), key=lambda o: (-o.documents, o.original)
    )
    shown = repeated[:_MAX_REPEATED_ROWS]
    return Table(
        f"Most repeated objects ({len(shown)} of {len(repeated)} in more than one document)",
        ("Id", "Type", "Documents"),
        tuple((o.original, o.kind, o.documents) for o in shown),
    )


def _collision_findings(collision: Collision) -> Iterator[Finding]:
    count = len(collision.variants)
    for number, labels in enumerate(collision.variants, start=1):
        message = f"Content {number} of {count} under id {collision.id}. " + (
            "References from files without this id lead to this content."
            if number == 1
            else "Analyzed as its own object, linked only from its own files."
        )
        locations = tuple(Location(file=label, identifiable_id=collision.id) for label in labels)
        yield Finding("id-collision", Severity.WARNING, message, locations)
