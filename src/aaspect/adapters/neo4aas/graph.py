import dataclasses
from collections.abc import Sequence

from neo4aas.core.client import AAS_NEO4J_MODEL_CONFIG, AASNeo4JClient
from neo4aas.core.utils import irdi_base
from neo4j.exceptions import DriverError, Neo4jError

from aaspect.domain.id_collisions import Environment, Occurrence, Rename

# Without the uniqueness constraint, so that collision variants can share their id once
# it is restored. Repeats are still merged by id during the import.
MODEL_CONFIG = dataclasses.replace(AAS_NEO4J_MODEL_CONFIG, enforce_unique_ids=False)

_STORE_OCCURRENCES = """
UNWIND $occurrences AS occurrence
MATCH (node:Identifiable {id: occurrence.id})
SET node.occurrence_count = occurrence.documents
"""
# Keeps each transaction small on corpora with hundreds of thousands of objects.
_OCCURRENCE_BATCH = 10_000

_RESTORE_IDENTIFIABLES = """
UNWIND $renames AS rename
MATCH (node:Identifiable {id: rename.temporary})
SET node.id = rename.original,
    node.collision_index = rename.index,
    node.id_base = CASE WHEN node.id_base IS NULL THEN null ELSE rename.original_base END
"""

_RESTORE_REFERENCES = """
UNWIND $renames AS rename
MATCH (reference:Reference {target_id: rename.temporary})
SET reference.keys_value = [rename.original] + reference.keys_value[1..],
    reference.target_id = rename.original,
    reference.target_id_base = rename.original_base
"""


class Neo4aasGraph:
    def __init__(self, client: AASNeo4JClient) -> None:
        self._client = client

    def upload(self, environment: Environment) -> None:
        try:
            self._client.upload_json(environment)
        except (DriverError, Neo4jError):
            raise
        except Exception as error:
            # neo4aas trusts the structure it is given; schema-invalid content fails with
            # whatever error the first unexpected value causes.
            raise ValueError(f"content cannot be stored: {type(error).__name__}") from error

    def link_references(self) -> None:
        self._client.resolve_references()

    def store_occurrences(self, occurrences: Sequence[Occurrence]) -> None:
        rows = [{"id": o.id, "documents": o.documents} for o in occurrences]
        for start in range(0, len(rows), _OCCURRENCE_BATCH):
            batch = rows[start : start + _OCCURRENCE_BATCH]
            self._client.execute_clause(_STORE_OCCURRENCES, params={"occurrences": batch})

    def restore_ids(self, renames: Sequence[Rename]) -> None:
        if not renames:
            return
        rows = [
            {
                "temporary": rename.temporary,
                "original": rename.original,
                "original_base": irdi_base(rename.original),
                "index": rename.index,
            }
            for rename in renames
        ]
        self._client.execute_clause(_RESTORE_IDENTIFIABLES, params={"renames": rows})
        self._client.execute_clause(_RESTORE_REFERENCES, params={"renames": rows})
