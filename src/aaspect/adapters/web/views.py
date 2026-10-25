"""Shapes report blocks for reading: repeated rules folded together, tables as charts."""

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


# A share chart with this many parts or fewer reads as one stacked bar.
_MAX_STACKED = 4
_MAX_TILES = 6


def chart_kind(table: Table) -> str:
    """How a table is drawn, judged from its shape alone: a single row as key figures, a
    few counts as tiles, shares as one stacked bar or as bars, attribute coverage as
    filled meters, anything else as a table."""
    columns = set(table.columns)
    if not table.rows:
        return "empty"
    if len(table.rows) == 1 and len(table.columns) <= _MAX_TILES:
        return "figures"
    if is_distribution(table):
        if columns >= {"Filled", "Of"}:
            return "filled"
        return "stack" if len(table.rows) <= _MAX_STACKED else "bars"
    numeric = all(isinstance(row[-1], int | float) for row in table.rows)
    if len(table.columns) == 2 and numeric and len(table.rows) <= _MAX_TILES:
        return "tiles"
    return "table"


def number(value: object) -> object:
    """Whole numbers with thousands separators; anything else as it is."""
    return f"{value:,}" if isinstance(value, int) and not isinstance(value, bool) else value
