from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from aaspect.domain.blocks import Finding, Location, Severity, Table
from aaspect.domain.corpus import AasDocument, ReadFailure
from aaspect.domain.environment_size import measure
from aaspect.domain.id_collisions import Collision, IdScan, Occurrence, RenamePlan
from aaspect.domain.report import Section, SectionStatus
from aaspect.ports.environment_parser import EnvironmentParser
from aaspect.ports.graph_store import CorpusGraph

SECTION_KEY = "graph-import"
SECTION_TITLE = "Graph import"
# A corpus can hold 100,000 ids; the long tail of small repeats says little.
_MAX_REPEATED_ROWS = 100
# One write per batch instead of per document; larger batches measured no faster.
# Memory grows with the number of JSON objects, about 1 kB each while neo4aas builds the
# nodes, and a few MB of crafted JSON hold millions of them. The largest real document
# seen has 42,000 objects. Bytes are capped too, for documents of few but long values.
_BATCH_DOCUMENTS = 50
_BATCH_BYTES = 32 * 2**20
_MAX_OBJECTS = 250_000
# Linking builds one query per distinct key count, each with one match per key, so a
# reference of thousands of keys costs the shared server a lot. Real ones have up to 3.
_MAX_REFERENCE_KEYS = 64
_TIME_LIMIT = "Not imported: the analysis reached its time limit."


@dataclass(frozen=True, slots=True)
class ImportResult:
    imported: int
    collisions: tuple[Collision, ...]
    not_imported: tuple[ReadFailure, ...]
    occurrences: tuple[Occurrence, ...]


def import_corpus(
    documents: Iterable[AasDocument],
    parser: EnvironmentParser,
    graph: CorpusGraph,
    expired: Callable[[], bool] = lambda: False,
) -> ImportResult:
    """Import every convertible document; colliding ids keep their variants apart. Once
    `expired` turns true, the remaining documents are reported as not imported."""
    ordered = sorted(documents, key=lambda document: document.label)
    scan = IdScan()
    importable: list[tuple[AasDocument, int]] = []
    failures: list[ReadFailure] = []
    for document in ordered:
        if expired():
            failures.append(ReadFailure(document.label, _TIME_LIMIT))
            continue
        try:
            environment = parser.parse(document)
            size = measure(environment)
            refusal = _too_large(size.objects, size.longest_reference)
            if refusal:
                failures.append(ReadFailure(document.label, refusal))
                continue
            scan.add(document.label, environment)
        except (ValueError, RecursionError) as error:
            failures.append(ReadFailure(document.label, f"Not imported: {error}"))
        else:
            importable.append((document, size.objects))
    plan = scan.plan()
    # Parsed a second time rather than kept: a corpus of 1 GB grows several times over
    # as Python objects, and only one batch needs to be in memory at once.
    for batch in _batches(importable):
        if expired():
            failures.extend(ReadFailure(document.label, _TIME_LIMIT) for document in batch)
        else:
            failures.extend(_upload(batch, parser, plan, graph))
    graph.link_references()
    # Documents that could not be uploaded are not in the graph, so they count nowhere.
    failed = {failure.source for failure in failures}
    occurrences = plan.occurrences(excluding=failed)
    graph.store_occurrences(occurrences)
    graph.restore_ids(plan.renames)
    failures.sort(key=lambda failure: failure.source)
    imported = len(ordered) - len(failures)
    return ImportResult(imported, plan.collisions(excluding=failed), tuple(failures), occurrences)


def _too_large(objects: int, longest_reference: int) -> str | None:
    if objects > _MAX_OBJECTS:
        return (
            f"Not imported: {objects:,} elements, more than the {_MAX_OBJECTS:,} one"
            " document may have."
        )
    if longest_reference > _MAX_REFERENCE_KEYS:
        return (
            f"Not imported: a reference with {longest_reference:,} keys, more than the"
            f" {_MAX_REFERENCE_KEYS} one may have."
        )
    return None


def _batches(documents: list[tuple[AasDocument, int]]) -> Iterator[list[AasDocument]]:
    """Up to `_BATCH_DOCUMENTS` documents, `_BATCH_BYTES` and `_MAX_OBJECTS`; a document
    over the byte cap goes alone."""
    batch: list[AasDocument] = []
    size = objects = 0
    for document, count in documents:
        length = len(document.content)
        full = len(batch) == _BATCH_DOCUMENTS
        if batch and (full or size + length > _BATCH_BYTES or objects + count > _MAX_OBJECTS):
            yield batch
            batch, size, objects = [], 0, 0
        batch.append(document)
        size += length
        objects += count
    if batch:
        yield batch


def _upload(
    batch: list[AasDocument], parser: EnvironmentParser, plan: RenamePlan, graph: CorpusGraph
) -> list[ReadFailure]:
    environments = [parser.parse(document) for document in batch]
    for environment in environments:
        plan.rewrite(environment)
    try:
        graph.upload(environments)
        return []
    except ValueError as error:
        if len(batch) == 1:
            return [ReadFailure(batch[0].label, f"Not imported: {error}")]
    # Nothing of a rejected batch is stored, so each document is tried on its own to find
    # the ones that cannot be.
    failures = []
    for document, environment in zip(batch, environments, strict=True):
        try:
            graph.upload([environment])
        except ValueError as error:
            failures.append(ReadFailure(document.label, f"Not imported: {error}"))
    return failures


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
            if number == 1 and not collision.first_missing
            else "Analyzed as its own object, linked only from its own files."
        )
        if collision.first_missing:
            message += (
                " The content first found under this id could not be imported, so"
                " references from files without this id lead nowhere."
            )
        locations = tuple(Location(file=label, identifiable_id=collision.id) for label in labels)
        yield Finding("id-collision", Severity.WARNING, message, locations)
