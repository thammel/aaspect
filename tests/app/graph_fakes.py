import copy
from collections.abc import Sequence

from aaspect.domain.corpus import AasDocument
from aaspect.domain.id_collisions import Environment, Rename


class FakeParser:
    """Returns a fresh copy of the environment configured per document label, so that a
    rewrite of one parse does not leak into the next; raises for any other label."""

    def __init__(self, environments: dict[str, Environment]) -> None:
        self.environments = environments

    def parse(self, document: AasDocument) -> Environment:
        if document.label not in self.environments:
            raise ValueError("not an AAS environment")
        return copy.deepcopy(self.environments[document.label])


class RecordingGraph:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def upload(self, environment: Environment) -> None:
        if environment.get("unstorable"):
            raise ValueError("content cannot be stored")
        self.calls.append(("upload", environment))

    def link_references(self) -> None:
        self.calls.append(("link", None))

    def restore_ids(self, renames: Sequence[Rename]) -> None:
        self.calls.append(("restore", tuple(renames)))
