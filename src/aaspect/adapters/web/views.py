"""Shapes report blocks for reading: repeated rules folded together, shares as bars."""

from collections.abc import Iterable
from dataclasses import dataclass

from aaspect.domain.blocks import Block, Finding, Severity, Table

_RANK = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
# Analytics distributions end with this column; they read better as bars than as rows.
_SHARE = "Share (%)"


@dataclass(frozen=True, slots=True)
class FindingGroup:
    """Every finding of one rule in a section; an id collision alone gives hundreds."""

    rule_id: str
    severity: Severity
    findings: tuple[Finding, ...]

    @property
    def places(self) -> int:
        return sum(len(finding.locations) for finding in self.findings)


def finding_groups(blocks: Iterable[Block]) -> list[FindingGroup]:
    """Worst severity first, then the most places."""
    grouped: dict[tuple[str, Severity], list[Finding]] = {}
    for block in blocks:
        if isinstance(block, Finding):
            grouped.setdefault((block.rule_id, block.severity), []).append(block)
    groups = [
        FindingGroup(rule_id, severity, tuple(findings))
        for (rule_id, severity), findings in grouped.items()
    ]
    return sorted(groups, key=lambda group: (_RANK[group.severity], -group.places))


def is_distribution(block: Block) -> bool:
    return isinstance(block, Table) and len(block.columns) > 1 and block.columns[-1] == _SHARE
