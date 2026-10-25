"""Which chart a table reads best as, judged from its shape alone."""

from aaspect.domain.blocks import Block, Table

# Analytics distributions end with this column; they read better as bars than as rows.
_SHARE = "Share (%)"


def is_distribution(block: Block) -> bool:
    """Ends in a share column holding numbers: charts add them up."""
    return (
        isinstance(block, Table)
        and len(block.columns) > 1
        and block.columns[-1] == _SHARE
        and all(_is_number(row[-1]) for row in block.rows)
    )


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


# A share chart with this many parts or fewer reads as one stacked bar.
_MAX_STACKED = 4
_MAX_TILES = 6


def chart_kind(table: Table) -> str:
    """How a table is drawn, judged from its shape alone: a single row as key figures,
    conformance counts as a scoreboard, a grid of whole numbers as a heat matrix, a few
    counts as tiles, shares as one stacked bar or as bars, attribute coverage as filled
    meters, anything else as a table."""
    columns = set(table.columns)
    if not table.rows:
        return "empty"
    if len(table.rows) == 1 and len(table.columns) <= _MAX_TILES:
        return "figures"
    if columns >= {"Submodels", "Conformant"}:
        return "scoreboard"
    if _is_matrix(table):
        return "matrix"
    if is_distribution(table):
        if columns >= {"Filled", "Of"}:
            return "filled"
        return "stack" if len(table.rows) <= _MAX_STACKED else "bars"
    numeric = all(_is_number(row[-1]) for row in table.rows)
    if len(table.columns) == 2 and numeric and len(table.rows) <= _MAX_TILES:
        return "tiles"
    return "table"


# A heat matrix needs enough columns to compare across; fewer read fine as a table.
_MIN_MATRIX_COLUMNS = 3


def _is_matrix(table: Table) -> bool:
    """Names in the first column and whole-number counts in at least three more: fractions,
    as in statistics, do not compare as heat."""
    if len(table.columns) - 1 < _MIN_MATRIX_COLUMNS:
        return False
    return all(
        isinstance(cell, int) and not isinstance(cell, bool)
        for row in table.rows
        for cell in row[1:]
    )


def number(value: object) -> object:
    """Whole numbers with thousands separators; anything else as it is."""
    return f"{value:,}" if isinstance(value, int) and not isinstance(value, bool) else value
