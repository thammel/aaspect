"""What a reader needs first from any report: which files have problems, and where.

Derived from findings alone, so it covers every analysis without knowing it. Counts are
of listed locations: an analysis that caps its locations, or names only the first file
of an object shared by many, makes them lower bounds.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass

from aaspect.domain.blocks import Finding, Location, Severity
from aaspect.domain.report import Report, Section, SectionStatus

_TOP_RULES = 6


@dataclass(frozen=True, slots=True)
class FileIssues:
    """One uploaded file with errors. `errors` holds (section title, error places)."""

    file: str
    errors: tuple[tuple[str, int], ...]
    warnings: int

    @property
    def total(self) -> int:
        return sum(count for _, count in self.errors)


@dataclass(frozen=True, slots=True)
class SectionTally:
    key: str
    title: str
    status: SectionStatus
    errors: int
    warnings: int
    notes: int


@dataclass(frozen=True, slots=True)
class RuleTally:
    section: str
    rule_id: str
    severity: Severity
    message: str
    places: int
    files: int


@dataclass(frozen=True, slots=True)
class Summary:
    files: int
    # Most errors first.
    failing: tuple[FileIssues, ...]
    sections: tuple[SectionTally, ...]
    top_rules: tuple[RuleTally, ...]
    # True only once every analysis has completed: a skipped or failed one proves nothing.
    complete: bool

    @property
    def passing(self) -> int:
        return self.files - len(self.failing)


def summarize(report: Report) -> Summary:
    tally = _Tally(_Owners(report.files))
    sections = tuple(tally.add(section) for section in report.sections)
    failing = sorted(
        (
            FileIssues(file, tuple(by_section.items()), tally.warnings[file])
            for file, by_section in tally.errors.items()
        ),
        key=lambda issues: (-issues.total, issues.file),
    )
    rules = sorted(
        tally.rules, key=lambda rule: (rule.severity is not Severity.ERROR, -rule.places)
    )
    return Summary(
        files=len(report.files),
        failing=tuple(failing),
        sections=sections,
        top_rules=tuple(rules[:_TOP_RULES]),
        complete=all(section.status is SectionStatus.COMPLETED for section in report.sections),
    )


class _Tally:
    def __init__(self, owners: "_Owners") -> None:
        self._owners = owners
        self.errors: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self.warnings: Counter[str] = Counter()
        self.rules: list[RuleTally] = []

    def add(self, section: Section) -> SectionTally:
        findings = [block for block in section.blocks if isinstance(block, Finding)]
        for finding in findings:
            self._add_finding(section.title, finding)
        count = Counter(finding.severity for finding in findings)
        return SectionTally(
            section.key,
            section.title,
            section.status,
            count[Severity.ERROR],
            count[Severity.WARNING],
            count[Severity.INFO],
        )

    def _add_finding(self, section: str, finding: Finding) -> None:
        named = [
            file
            for file in (self._owners.of(location) for location in finding.locations)
            if file is not None
        ]
        if finding.severity is Severity.INFO:
            return
        if finding.severity is Severity.ERROR:
            for file, places in Counter(named).items():
                self.errors[file][section] += places
        else:
            self.warnings.update(named)
        self.rules.append(
            RuleTally(
                section,
                finding.rule_id,
                finding.severity,
                finding.message,
                len(finding.locations),
                len(set(named)),
            )
        )


class _Owners:
    """Maps a location to the uploaded file it lies in. A document inside an AASX package
    is labelled `package:part`."""

    def __init__(self, files: tuple[str, ...]) -> None:
        self._files = set(files)

    def of(self, location: Location) -> str | None:
        label = location.file
        if label is None:
            return None
        if label in self._files:
            return label
        # An upload's own name may hold a colon too, so every split point is tried.
        start = label.find(":")
        while start != -1:
            if label[:start] in self._files:
                return label[:start]
            start = label.find(":", start + 1)
        return None
