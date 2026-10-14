import json
import os
import unittest

from neo4aas.core.client import AASNeo4JClient
from neo4j import Record

from aaspect.adapters.neo4aas.graph import MODEL_CONFIG, Neo4aasGraph
from aaspect.adapters.neo4aas.parser import Neo4aasEnvironmentParser
from aaspect.app.import_corpus import import_corpus
from aaspect.domain.corpus import AasDocument, DocumentFormat

# A server with the DozerDB plugin, e.g. the one from compose.yaml with its port published.
_URI = os.environ.get("AASPECT_TEST_NEO4J_URI")
_PASSWORD = os.environ.get("AASPECT_TEST_NEO4J_PASSWORD", "")


class TestUploadErrors(unittest.TestCase):
    def test_malformed_content_raises_value_error(self) -> None:
        graph = Neo4aasGraph(AASNeo4JClient(uri="", user="", model_config=MODEL_CONFIG))
        with self.assertRaises(ValueError):
            graph.upload({"submodels": "not a list"})


def _file(name: str, shell_id: str, id_short: str) -> AasDocument:
    reference = {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "urn:sm"}]}
    environment = {
        "assetAdministrationShells": [
            {
                "id": shell_id,
                "modelType": "AssetAdministrationShell",
                "assetInformation": {"assetKind": "Instance", "globalAssetId": "urn:asset"},
                "submodels": [reference],
            }
        ],
        "submodels": [{"id": "urn:sm", "idShort": id_short, "modelType": "Submodel"}],
    }
    return AasDocument(name, DocumentFormat.JSON, json.dumps(environment).encode())


def _count(client: AASNeo4JClient, query: str) -> int:
    record = client.execute_clause(query, single=True)
    assert isinstance(record, Record)
    return record["c"]


@unittest.skipUnless(_URI, "set AASPECT_TEST_NEO4J_URI to run against a graph database")
class TestImportIntoNeo4j(unittest.TestCase):
    """Works in the server's default database, and only while it is empty."""

    def setUp(self) -> None:
        assert _URI
        self.client = AASNeo4JClient(_URI, "neo4j", _PASSWORD, model_config=MODEL_CONFIG)
        self.addCleanup(self.client.driver.close)
        if _count(self.client, "MATCH (n) RETURN count(n) AS c"):
            self.skipTest("the default database is not empty")
        self.addCleanup(self.client.execute_clause, "MATCH (n) DETACH DELETE n")

    def test_each_shell_links_to_the_variant_from_its_own_file(self) -> None:
        documents = [
            _file("a.json", "urn:aas-a", "A"),
            _file("b.json", "urn:aas-b", "B"),
            _file("c.json", "urn:aas-c", "A"),
        ]

        result = import_corpus(documents, Neo4aasEnvironmentParser(), Neo4aasGraph(self.client))

        rows = self.client.execute_clause(
            "MATCH (shell:AssetAdministrationShell)-->(:Reference)-[:references]->(sm:Submodel)"
            " RETURN shell.id AS shell, sm.id AS id, sm.idShort AS idShort,"
            " sm.collision_index AS index ORDER BY shell"
        )
        self.assertEqual(
            [tuple(row.values()) for row in rows or []],
            [
                ("urn:aas-a", "urn:sm", "A", None),
                ("urn:aas-b", "urn:sm", "B", 1),
                ("urn:aas-c", "urn:sm", "A", None),
            ],
        )
        self.assertEqual(len(result.collisions), 1)
        counts = self.client.execute_clause(
            "MATCH (sm:Submodel) RETURN sm.idShort AS idShort, sm.occurrence_count AS count"
            " ORDER BY idShort"
        )
        self.assertEqual([tuple(row.values()) for row in counts or []], [("A", 2), ("B", 1)])
        references = self.client.execute_clause(
            "MATCH (r:Reference) WHERE r.target_id = 'urn:sm' RETURN DISTINCT"
            " r.keys_value[0] AS key, r.target_id_base AS base"
        )
        self.assertEqual([tuple(row.values()) for row in references or []], [("urn:sm", "urn:sm")])
        leftover = _count(
            self.client,
            "MATCH (n) WHERE n.id CONTAINS '__collision' OR n.target_id CONTAINS '__collision'"
            " RETURN count(n) AS c",
        )
        self.assertEqual(leftover, 0)


if __name__ == "__main__":
    unittest.main()
