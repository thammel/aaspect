from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import Protocol

from aaspect.domain.id_collisions import Environment, Rename


class CorpusGraph(Protocol):
    """The graph database of one analysis."""

    def upload(self, environment: Environment) -> None:
        """Raises `ValueError` for an environment whose content cannot be stored; a
        failure of the database itself raises anything else."""
        ...

    def link_references(self) -> None:
        """Link every Reference to its target. Call once, after the last upload."""
        ...

    def restore_ids(self, renames: Sequence[Rename]) -> None:
        """Give renamed Identifiables, and the References naming them, their original id
        back. Afterward an id may belong to several nodes, so nothing may link again."""
        ...


class GraphStore(Protocol):
    def open(self, analysis_id: str) -> AbstractContextManager[CorpusGraph]:
        """A new, empty graph for this analysis, deleted when the context exits."""
        ...
