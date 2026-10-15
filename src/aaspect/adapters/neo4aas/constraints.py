"""Run the neo4aas constraint checker and place each violation in its Identifiable."""

from collections.abc import Iterator

from neo4aas.core.client import AASNeo4JClient
from neo4aas.core.validation import AASConstraintChecker
from neo4aas.core.validation import ConstraintViolation as CheckerViolation

from aaspect.domain.constraints.violations import (
    ConstraintResult,
    ConstraintViolation,
    Place,
    RuleResult,
)
from aaspect.domain.metamodel import MetamodelVersion

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
    MATCH path = (node) ((child)<-[edge]-(parent) WHERE type(edge) <> "references"){0,64}
                 (owner:Identifiable)
    RETURN owner, [n IN reverse(nodes(path))[1..] WHERE n.idShort IS NOT NULL | n.idShort]
           AS id_shorts
    LIMIT $limit
}
RETURN node_id, owner.id AS id, coalesce(owner.collision_index, 0) AS collision_index,
       id_shorts
"""


def check_constraints(client: AASNeo4JClient, version: MetamodelVersion) -> ConstraintResult:
    report = AASConstraintChecker(client, version.value).check_all()
    found: dict[str, list[CheckerViolation]] = {rule: [] for rule in report.checked_constraints}
    for violation in report.violations:
        found[violation.constraint_id].append(violation)
    listed = {rule: violations[:_MAX_LISTED] for rule, violations in found.items()}
    nodes = {_node_id(v.details) for violations in listed.values() for v in violations}
    places = _places(client, {node for node in nodes if node is not None})
    return ConstraintResult(
        tuple(
            RuleResult(
                rule,
                len(found[rule]),
                tuple(_located(violation, places) for violation in violations),
            )
            for rule, violations in listed.items()
        )
    )


def _located(violation: CheckerViolation, places: dict[str, list[Place]]) -> ConstraintViolation:
    node = _node_id(violation.details)
    found = places.get(node, []) if node else []
    return ConstraintViolation(tuple(found[:_MAX_PLACES]), len(found) > _MAX_PLACES)


def _node_id(details: dict) -> str | None:
    return next((details[key] for key in _NODE_KEYS if isinstance(details.get(key), str)), None)


def _places(client: AASNeo4JClient, node_ids: set[str]) -> dict[str, list[Place]]:
    places: dict[str, list[Place]] = {}
    for batch in _batches(sorted(node_ids)):
        # One more than kept, to tell a capped list from a complete one.
        params = {"node_ids": batch, "limit": _MAX_PLACES + 1}
        for record in client.execute_clause(_PLACES, params=params) or []:
            place = Place(
                str(record["id"]), record["collision_index"], ".".join(record["id_shorts"])
            )
            places.setdefault(record["node_id"], []).append(place)
    return places


def _batches(items: list[str]) -> Iterator[list[str]]:
    for start in range(0, len(items), _NODE_BATCH):
        yield items[start : start + _NODE_BATCH]
