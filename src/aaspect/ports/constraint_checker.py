from typing import Protocol

from aaspect.domain.constraints.violations import ConstraintResult
from aaspect.domain.metamodel import MetamodelVersion


class ConstraintChecker(Protocol):
    def check_constraints(self, version: MetamodelVersion) -> ConstraintResult:
        """Check the whole graph against every constraint of `version`. Call after the
        import has finished."""
        ...
