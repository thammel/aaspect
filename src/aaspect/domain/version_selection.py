"""Which metamodel version a document is validated against, decided per document.

A corpus mixes versions. Validating it against one version would bury the report in
violations that only mean "other version".
"""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from aaspect.domain.blocks import Table
from aaspect.domain.corpus import AasDocument
from aaspect.domain.metamodel import NEWEST_FIRST, MetamodelVersion
from aaspect.domain.schema_check import SchemaViolation


class VersionBasis(StrEnum):
    DECLARED = "declared"
    REQUESTED = "requested"
    AUTO = "auto"


@dataclass(frozen=True, slots=True)
class VersionOutcome:
    version: MetamodelVersion
    basis: VersionBasis
    violations: tuple[SchemaViolation, ...]

    @property
    def valid(self) -> bool:
        return not self.violations


def select_version(
    document: AasDocument,
    requested: MetamodelVersion | None,
    validate: Callable[[MetamodelVersion], Sequence[SchemaViolation]],
) -> VersionOutcome:
    """Validate `document` against the version it should be judged by.

    A declared version wins over the requested one. On auto, versions are tried newest
    first and the first valid one is kept, so older versions stay unchecked. If none is
    valid, the version with the fewest violations is reported; on a tie, the newer one.
    """
    if document.declared_version is not None:
        version = document.declared_version
        return VersionOutcome(version, VersionBasis.DECLARED, tuple(validate(version)))
    if requested is not None:
        return VersionOutcome(requested, VersionBasis.REQUESTED, tuple(validate(requested)))
    attempts: list[VersionOutcome] = []
    for version in NEWEST_FIRST:
        outcome = VersionOutcome(version, VersionBasis.AUTO, tuple(validate(version)))
        if outcome.valid:
            return outcome
        attempts.append(outcome)
    return min(attempts, key=lambda attempt: len(attempt.violations))


_BASIS_TEXT = {
    VersionBasis.DECLARED: "XML namespace",
    VersionBasis.REQUESTED: "chosen by user",
}


def _basis_text(outcome: VersionOutcome) -> str:
    if outcome.basis is not VersionBasis.AUTO:
        return _BASIS_TEXT[outcome.basis]
    if outcome.valid:
        return "auto: newest valid version, older versions not checked"
    return "auto: no version valid, fewest violations"


def version_tables(results: Sequence[tuple[str, VersionOutcome]]) -> tuple[Table, Table]:
    """The version distribution across the corpus, and the version of each file."""
    counts = Counter(outcome.version for _, outcome in results)
    distribution = Table(
        title="Metamodel versions",
        columns=("Version", "Files"),
        rows=tuple((version.value, counts[version]) for version in NEWEST_FIRST if counts[version]),
    )
    per_file = Table(
        title="Version per file",
        columns=("File", "Version", "Determined by", "Valid"),
        rows=tuple(
            (file, outcome.version.value, _basis_text(outcome), "yes" if outcome.valid else "no")
            for file, outcome in results
        ),
    )
    return distribution, per_file
