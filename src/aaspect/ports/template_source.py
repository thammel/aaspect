from collections.abc import Sequence
from typing import Protocol

from aaspect.domain.templates.catalogue import TemplateFile


class TemplateSource(Protocol):
    def templates(self) -> Sequence[TemplateFile]:
        """Every template file available. Raises `ShownError` when none can be had, e.g.
        while their download fails."""
        ...
