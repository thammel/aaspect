"""Run the neo4aas constraint checker and place each violation in its Identifiable."""

import logging
from collections.abc import Callable, Iterable, Iterator, Sequence

from neo4aas.core.client import AASNeo4JClient
from neo4aas.core.validation import AASConstraintChecker
from neo4aas.core.validation import ConstraintViolation as CheckerViolation
from neo4j.exceptions import DriverError

from aaspect.domain.constraints.violations import (
    ConstraintResult,
    ConstraintViolation,
    Place,
    RuleResult,
    RuleStatus,
)
from aaspect.domain.metamodel import MetamodelVersion

logger = logging.getLogger(__name__)

# The detail naming the violating element, most specific first: a check on a list child
# also names the list, one on a duplicate idShort only the parent holding both.
_NODE_KEYS = (
    "node_id",
    "child_node_id",
    "ref_node_id",
    "adm_node_id",
    "list_node_id",
    "op_node_id",
    "parent_node_id",
)
# A Reference is stored once for every element holding the same one, so a wrong
# semanticId can belong to thousands of objects.
_MAX_PLACES = 100
# Located per rule; the rest are only counted. Keeps memory and lookups bounded however
# many violations a crafted corpus produces.
_MAX_LISTED = 1_000
_NODE_BATCH = 1_000
# Walks up the containment edges only: a Reference links to its target by `references`,
# which would make an AAS appear to contain its submodels. Real nesting is far below 64.
_PLACES = """
UNWIND $node_ids AS node_id
MATCH (node) WHERE elementId(node) = node_id
CALL (node) {
    MATCH (node) ((child)<-[edge]-(parent) WHERE type(edge) <> "references"){0,64}
          (owner:Identifiable)
    RETURN owner,
           [step IN range(size(edge) - 1, 0, -1) | [child[step].idShort, edge[step].list_index]]
           AS steps
    LIMIT $limit
}
RETURN node_id, owner.id AS id, owner.collision_index AS collision_index, steps
"""


def check_constraints(
    client: AASNeo4JClient, version: MetamodelVersion, expired: Callable[[], bool]
) -> ConstraintResult:
    checker = AASConstraintChecker(client, version.value)
    rules = []
    for rule in checker.constraint_ids:
        if expired():
            rules.append(RuleResult(rule, 0, status=RuleStatus.NOT_CHECKED))
            continue
        try:
            found = checker.check([rule]).violations
        except DriverError:
            raise
        except Exception:
            # One rule tripping over unexpected content must not take the others down.
            logger.warning("Constraint %s could not be checked", rule, exc_info=True)
            rules.append(RuleResult(rule, 0, status=RuleStatus.FAILED))
            continue
        listed = found[:_MAX_LISTED]
        nodes = {_node_id(violation.details) for violation in listed}
        places = _places(client, {node for node in nodes if node is not None}, expired)
        located = tuple(_located(violation, places) for violation in listed)
        rules.append(RuleResult(rule, len(found), located))
    return ConstraintResult(tuple(rules))


def _located(violation: CheckerViolation, places: dict[str, list[Place]]) -> ConstraintViolation:
    node = _node_id(violation.details)
    found = places.get(node, []) if node else []
    # AASd-022 and AASd-134 name the parent; the repeated idShort says which children.
    repeated = violation.details.get("duplicate_id_short")
    if repeated is not None:
        found = [_below(place, [(repeated, None)]) for place in found]
    return ConstraintViolation(tuple(found[:_MAX_PLACES]), len(found) > _MAX_PLACES)


def _node_id(details: dict) -> str | None:
    return next((details[key] for key in _NODE_KEYS if isinstance(details.get(key), str)), None)


def _places(
    client: AASNeo4JClient, node_ids: set[str], expired: Callable[[], bool]
) -> dict[str, list[Place]]:
    """Places per node; nodes still waiting when `expired` turns true get none."""
    places: dict[str, list[Place]] = {}
    for batch in _batches(sorted(node_ids)):
        if expired():
            break
        # One more than kept, to tell a capped list from a complete one.
        params = {"node_ids": batch, "limit": _MAX_PLACES + 1}
        for record in client.execute_clause(_PLACES, params=params) or []:
            place = place_of(record["id"], record["collision_index"], record["steps"])
            places.setdefault(record["node_id"], []).append(place)
    return places


def place_of(owner_id: object, collision_index: object, steps: list[list]) -> Place:
    """A place from what the graph holds. Any value may come from a file, so none is
    trusted to have the type the metamodel gives it."""
    index = collision_index if type(collision_index) is int else 0
    return _below(Place(str(owner_id), index, ""), steps)


def _below(place: Place, steps: Iterable[Sequence]) -> Place:
    """`place` extended by (idShort, position in a list) steps, as in `a.list[3].b`."""
    path = place.element_path
    for id_short, list_index in steps:
        if type(list_index) is int:
            path += f"[{list_index}]"
        elif id_short is not None:
            path += ("." if path else "") + str(id_short)
    return Place(place.identifiable_id, place.collision_index, path)


def _batches(items: list[str]) -> Iterator[list[str]]:
    for start in range(0, len(items), _NODE_BATCH):
        yield items[start : start + _NODE_BATCH]
