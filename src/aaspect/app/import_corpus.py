from collections.abc import Iterable
from dataclasses import dataclass

from aaspect.domain.corpus import AasDocument, ReadFailure
from aaspect.domain.id_collisions import Collision, IdScan
from aaspect.ports.environment_parser import EnvironmentParser
from aaspect.ports.graph_store import CorpusGraph


@dataclass(frozen=True, slots=True)
class ImportResult:
    collisions: tuple[Collision, ...]
    not_imported: tuple[ReadFailure, ...]


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
    graph.restore_ids(plan.renames)
    return ImportResult(plan.collisions, tuple(sorted(failures, key=lambda f: f.source)))
