from collections.abc import Callable, Iterable
from functools import partial

from aaspect.domain.blocks import Finding, Location, Severity
from aaspect.domain.corpus import AasDocument, Corpus
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Section, SectionStatus
from aaspect.domain.schema_check import group_violations
from aaspect.domain.version_selection import VersionOutcome, select_version, version_tables
from aaspect.ports.schema_validator import SchemaValidator

SECTION_KEY = "schema"
SECTION_TITLE = "Schema check"

# `map`, or a pool's `map` to validate documents in parallel. Order must be kept.
type MapDocuments = Callable[
    [Callable[[AasDocument], VersionOutcome], Iterable[AasDocument]], Iterable[VersionOutcome]
]


def check_schema(
    corpus: Corpus,
    validator: SchemaValidator,
    requested: MetamodelVersion | None,
    map_documents: MapDocuments = map,
) -> Section:
    def outcome(document: AasDocument) -> VersionOutcome:
        return select_version(document, requested, partial(validator.validate, document))

    labels = [document.label for document in corpus.documents]
    outcomes = list(zip(labels, map_documents(outcome, corpus.documents), strict=True))
    unreadable = tuple(
        Finding("unreadable-file", Severity.ERROR, failure.reason, (Location(file=failure.source),))
        for failure in corpus.failures
    )
    violations = group_violations(
        (file, outcome.version, outcome.violations) for file, outcome in outcomes
    )
    return Section(
        key=SECTION_KEY,
        title=SECTION_TITLE,
        status=SectionStatus.COMPLETED,
        blocks=(*version_tables(outcomes), *unreadable, *violations),
    )
