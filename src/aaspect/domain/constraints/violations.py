"""Metamodel constraint violations as the graph reports them."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Place:
    """An element inside a stored Identifiable. `collision_index` tells collision variants
    apart (0 for the content that kept the id); `element_path` is empty for the
    Identifiable itself."""

    identifiable_id: str
    collision_index: int
    element_path: str


@dataclass(frozen=True, slots=True)
class ConstraintViolation:
    """One violating element, with every Identifiable it belongs to: a Reference is stored
    once and shared by all elements that hold the same one. `more_places` is set when
    there were more than the ones listed; no places means none were found."""

    places: tuple[Place, ...]
    more_places: bool = False


@dataclass(frozen=True, slots=True)
class RuleResult:
    """What one rule found: `total` counts every violation, `violations` lists at most a
    capped number of them."""

    rule_id: str
    total: int
    violations: tuple[ConstraintViolation, ...] = ()


@dataclass(frozen=True, slots=True)
class ConstraintResult:
    """One result per checked rule, in check order."""

    rules: tuple[RuleResult, ...]
