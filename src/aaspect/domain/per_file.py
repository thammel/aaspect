"""One uploaded file's share of a report: the findings and table rows that name it."""

from dataclasses import replace

from aaspect.domain.blocks import Block, Finding, Location, Table
from aaspect.domain.report import Report, Section


class Owners:
    """Maps a document label to the uploaded file it lies in. A document inside an AASX
    package is labelled `package:part`."""

    def __init__(self, files: tuple[str, ...]) -> None:
        self._files = set(files)

    def of(self, label: str | None) -> str | None:
        if label is None:
            return None
        if label in self._files:
            return label
        # Upload names never hold a colon (the web adapter replaces it), so the package is
        # everything before the first one. Trying every colon instead costs the square of a
        # label's length, and part names come from the files.
        package, separator, _ = label.partition(":")
        return package if separator and package in self._files else None


def file_sections(report: Report, file: str) -> tuple[Section, ...]:
    """Every section narrowed to `file`: findings keep only its locations, tables only the
    rows whose first cell names it. Corpus-wide tables, such as distributions, drop out."""
    owners = Owners(report.files)
    return tuple(
        replace(section, blocks=tuple(_narrowed(section.blocks, owners, file)))
        for section in report.sections
    )


def _narrowed(blocks: tuple[Block, ...], owners: Owners, file: str) -> list[Block]:
    kept: list[Block] = []
    for block in blocks:
        if isinstance(block, Finding):
            locations = tuple(loc for loc in block.locations if _in(loc, owners, file))
            if locations:
                kept.append(replace(block, locations=locations))
        else:
            rows = tuple(
                row for row in block.rows if isinstance(row[0], str) and owners.of(row[0]) == file
            )
            if rows and all(row[0] == file for row in rows) and len(block.columns) > 1:
                # A column naming the file on every row says nothing on that file's page.
                kept.append(Table(block.title, block.columns[1:], tuple(r[1:] for r in rows)))
            elif rows:
                kept.append(Table(block.title, block.columns, rows))
    return kept


def _in(location: Location, owners: Owners, file: str) -> bool:
    return owners.of(location.file) == file
