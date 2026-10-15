import json
import os
import unittest
from collections.abc import Callable
from typing import cast

from neo4aas.core.client import AASNeo4JClient
from neo4j.exceptions import ServiceUnavailable

from aaspect.adapters.neo4aas.constraints import (
    _affected,
    _node_id,
    check_constraints,
    place_of,
)
from aaspect.adapters.neo4aas.graph import MODEL_CONFIG
from aaspect.adapters.neo4aas.parser import Neo4aasEnvironmentParser
from aaspect.adapters.neo4aas.store import DozerDbStore
from aaspect.app.import_corpus import import_corpus
from aaspect.domain.constraints.violations import Place, RuleStatus
from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import MetamodelVersion

_URI = os.environ.get("AASPECT_TEST_NEO4J_URI")
_PASSWORD = os.environ.get("AASPECT_TEST_NEO4J_PASSWORD", "")

# Wrong first key for an ExternalReference (AASd-122); stored once, held by two elements.
_BAD_SEMANTIC_ID = {"type": "ExternalReference", "keys": [{"type": "Submodel", "value": "x"}]}


class TestNodeId(unittest.TestCase):
    def test_takes_the_most_specific_element(self) -> None:
        self.assertEqual(_node_id({"list_node_id": "l", "child_node_id": "c"}), "c")
        self.assertEqual(_node_id({"parent_node_id": "p", "id_short": "a"}), "p")
        self.assertIsNone(_node_id({"identifiable_id": "urn:x"}))


class TestPlaceOf(unittest.TestCase):
    def test_path_with_list_positions(self) -> None:
        place = place_of("urn:sm", 2, [["Group", None], ["L", None], [None, 3], ["x", None]])
        self.assertEqual(place, Place("urn:sm", 2, "Group.L[3].x"))

    def test_values_of_the_wrong_type_from_a_file(self) -> None:
        place = place_of(17, [1], [[123, None], [["a"], True], [None, None]])
        self.assertEqual(place, Place("17", 0, "123.['a']"))

    def test_the_identifiable_itself(self) -> None:
        self.assertEqual(place_of("urn:sm", None, []), Place("urn:sm", 0, ""))


class _Client:
    """Answers every checker query with no rows, except the idShort query of AASd-002,
    which gets a value the checker does not expect, or `error`."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    model_config = MODEL_CONFIG

    def execute_clause(self, query: str, single: bool = False, params: dict | None = None):
        if "n.idShort AS id_short" in query:
            if self.error:
                raise self.error
            return [{"node_id": "n", "node_labels": [], "id_short": 5}]
        return []


def _check(client: _Client, version: MetamodelVersion, expired: Callable[[], bool]):
    return check_constraints(cast(AASNeo4JClient, client), version, expired)


class TestRuleByRule(unittest.TestCase):
    def test_a_failing_rule_does_not_stop_the_others(self) -> None:
        with self.assertLogs("aaspect.adapters.neo4aas.constraints", "WARNING"):
            result = _check(_Client(), MetamodelVersion.V3_1, lambda: False)
        statuses = {rule.rule_id: rule.status for rule in result.rules}
        self.assertEqual(statuses.pop("AASd-002"), RuleStatus.FAILED)
        self.assertEqual(set(statuses.values()), {RuleStatus.CHECKED})

    def test_a_lost_database_still_fails_the_step(self) -> None:
        with self.assertRaises(ServiceUnavailable):
            _check(
                _Client(ServiceUnavailable("gone")),
                MetamodelVersion.V3_1,
                lambda: False,
            )

    def test_rules_after_the_time_limit_are_not_checked(self) -> None:
        turns = iter([False, False])
        result = _check(
            _Client(),
            MetamodelVersion.V3_2,
            lambda: next(turns, True),
        )
        statuses = [rule.status for rule in result.rules]
        self.assertEqual(statuses[:2], [RuleStatus.FAILED, RuleStatus.CHECKED])
        self.assertEqual(set(statuses[2:]), {RuleStatus.NOT_CHECKED})


class TestAffected(unittest.TestCase):
    def test_past_the_deadline_each_violation_counts_once(self) -> None:
        client = cast(AASNeo4JClient, _Client())
        self.assertEqual(_affected(client, ["a", "b", None], lambda: True), 3)


def _property(id_short: str) -> dict:
    return {
        "idShort": id_short,
        "modelType": "Property",
        "valueType": "xs:string",
        "semanticId": _BAD_SEMANTIC_ID,
    }


def _document(name: str, submodel_id: str, *elements: dict) -> AasDocument:
    collection = {"idShort": "Group", "modelType": "SubmodelElementCollection", "value": elements}
    submodel = {"id": submodel_id, "modelType": "Submodel", "submodelElements": [collection]}
    environment = {"submodels": [submodel]}
    return AasDocument(name, DocumentFormat.JSON, json.dumps(environment).encode())


@unittest.skipUnless(_URI, "set AASPECT_TEST_NEO4J_URI to run against a DozerDB server")
class TestConstraintsInNeo4j(unittest.TestCase):
    def setUp(self) -> None:
        assert _URI
        store = DozerDbStore(_URI, "neo4j", _PASSWORD)
        self.addCleanup(store.close)
        self.graph = self.enterContext(store.open())

    def test_paths_show_list_positions_and_repeated_names(self) -> None:
        listed = {
            "idShort": "L",
            "modelType": "SubmodelElementList",
            "typeValueListElement": "Property",
            "valueTypeListElement": "xs:string",
            "value": [
                {"modelType": "Property", "valueType": "xs:string"},
                {"modelType": "Range", "valueType": "xs:int"},
            ],
        }
        twice = {"idShort": "twice", "modelType": "Property", "valueType": "xs:string"}
        documents = [_document("a.json", "urn:sm", listed, twice, dict(twice))]
        import_corpus(documents, Neo4aasEnvironmentParser(), self.graph)

        result = self.graph.check_constraints(MetamodelVersion.V3_1, lambda: False)

        paths = {
            rule.rule_id: {p.element_path for v in rule.violations for p in v.places}
            for rule in result.rules
            if rule.total
        }
        self.assertEqual(paths["AASd-108"], {"Group.L[1]"})
        self.assertEqual(paths["AASd-022"], {"Group.twice"})

    def test_an_id_short_that_is_not_text_is_still_checked(self) -> None:
        number = {"idShort": 123, "modelType": "Property", "valueType": "xs:string"}
        import_corpus(
            [_document("a.json", "urn:sm", number)], Neo4aasEnvironmentParser(), self.graph
        )

        result = self.graph.check_constraints(MetamodelVersion.V3_1, lambda: False)

        [rule] = [rule for rule in result.rules if rule.rule_id == "AASd-002"]
        self.assertEqual(rule.violations[0].places, (Place("urn:sm", 0, "Group.123"),))

    def test_a_shell_does_not_contain_its_submodels(self) -> None:
        shell = {
            "id": "urn:aas",
            "modelType": "AssetAdministrationShell",
            "assetInformation": {"assetKind": "Instance", "globalAssetId": "urn:asset"},
            "submodels": [
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "urn:sm"}]}
            ],
        }
        document = _document("a.json", "urn:sm", _property("1bad"))
        environment = json.loads(document.content)
        environment["assetAdministrationShells"] = [shell]
        content = json.dumps(environment).encode()
        import_corpus(
            [AasDocument("a.json", DocumentFormat.JSON, content)],
            Neo4aasEnvironmentParser(),
            self.graph,
        )

        result = self.graph.check_constraints(MetamodelVersion.V3_1, lambda: False)

        [rule] = [rule for rule in result.rules if rule.rule_id == "AASd-002"]
        self.assertEqual(
            [violation.places for violation in rule.violations],
            [(Place("urn:sm", 0, "Group.1bad"),)],
        )

    def test_violations_are_placed_in_their_own_variant(self) -> None:
        documents = [
            _document("a.json", "urn:sm", _property("1bad")),
            _document("b.json", "urn:sm", _property("good"), _property("2bad")),
        ]
        import_corpus(documents, Neo4aasEnvironmentParser(), self.graph)

        result = self.graph.check_constraints(MetamodelVersion.V3_1, lambda: False)

        by_rule = {
            rule.rule_id: {place for violation in rule.violations for place in violation.places}
            for rule in result.rules
        }
        self.assertEqual(
            by_rule["AASd-002"],
            {Place("urn:sm", 0, "Group.1bad"), Place("urn:sm", 1, "Group.2bad")},
        )
        self.assertEqual(
            by_rule["AASd-122"],
            {
                Place("urn:sm", 0, "Group.1bad"),
                Place("urn:sm", 1, "Group.good"),
                Place("urn:sm", 1, "Group.2bad"),
            },
        )
        self.assertEqual(
            {rule.rule_id: rule.total for rule in result.rules if rule.total},
            {"AASd-002": 2, "AASd-122": 3, "AASd-124": 3},
        )


if __name__ == "__main__":
    unittest.main()
