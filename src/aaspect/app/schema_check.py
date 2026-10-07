from functools import partial

from aaspect.domain.blocks import Finding, Location, Severity
from aaspect.domain.corpus import Corpus
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Section, SectionStatus
from aaspect.domain.schema_check import group_violations
from aaspect.domain.version_selection import select_version, version_tables
from aaspect.ports.schema_validator import SchemaValidator

SECTION_KEY = "schema"
SECTION_TITLE = "Schema check"


def check_schema(
    corpus: Corpus, validator: SchemaValidator, requested: MetamodelVersion | None
) -> Section:
    outcomes = [
        (document.label, select_version(document, requested, partial(validator.validate, document)))
        for document in corpus.documents
    ]
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
