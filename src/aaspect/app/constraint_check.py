"""Check an imported corpus against the metamodel constraints of one version."""

from collections.abc import Callable, Iterator, Sequence

from aaspect.app.import_corpus import ImportResult
from aaspect.domain.blocks import Finding, Location, Severity, Table
from aaspect.domain.constraints.corpus_version import CorpusVersion, corpus_version
from aaspect.domain.constraints.findings import violation_findings
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Section, SectionStatus
from aaspect.domain.version_selection import VersionChoice
from aaspect.ports.constraint_checker import ConstraintChecker

SECTION_KEY = "constraints"
SECTION_TITLE = "Metamodel constraints"


def check_constraints(
    checker: ConstraintChecker,
    imported: ImportResult,
    choice: VersionChoice,
    versions: Sequence[tuple[str, MetamodelVersion | None]] | None,
    expired: Callable[[], bool] = lambda: False,
) -> Section:
    """`versions` holds each document's label and the version the schema check found,
    None if the schema check failed; only documents in the graph count toward the version
    used."""
    if expired():
        return Section(
            SECTION_KEY,
            SECTION_TITLE,
            SectionStatus.SKIPPED,
            reason="The analysis reached its time limit.",
        )
    missing = {failure.source for failure in imported.not_imported}
    present = None if versions is None else [v for v in versions if v[0] not in missing]
    chosen = corpus_version(choice, present)
    result = checker.check_constraints(chosen.version)
    occurrences = {(o.original, o.index): o for o in imported.occurrences}
    total = sum(rule.total for rule in result.rules)
    summary = Table(
        "Constraint check",
        ("Metamodel version", "Determined by", "Constraints checked", "Violations"),
        ((chosen.version.value, chosen.basis, len(result.rules), total),),
    )
    per_rule = Table(
        "Violations per constraint",
        ("Constraint", "Violations"),
        tuple((rule.rule_id, rule.total) for rule in result.rules),
    )
    blocks = (
        summary,
        per_rule,
        *_other_versions(chosen),
        *violation_findings(result.rules, occurrences),
    )
    return Section(SECTION_KEY, SECTION_TITLE, SectionStatus.COMPLETED, blocks)


def _other_versions(chosen: CorpusVersion) -> Iterator[Finding]:
    by_version: dict[MetamodelVersion | None, list[str]] = {}
    for label, version in chosen.others:
        by_version.setdefault(version, []).append(label)
    for version, labels in by_version.items():
        found = f"version {version.value}" if version else "no version"
        yield Finding(
            "other-version",
            Severity.WARNING,
            f"Determined as {found}, but checked by the rules of version"
            f" {chosen.version.value}, like the whole corpus. Results for these files may"
            " be inaccurate.",
            tuple(Location(file=label) for label in labels),
        )
