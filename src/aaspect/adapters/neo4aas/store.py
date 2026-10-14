import logging
import re
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import LiteralString, cast

from neo4aas.core.client import AASNeo4JClient
from neo4j import GraphDatabase, Record

from aaspect.adapters.neo4aas.graph import MODEL_CONFIG, Neo4aasGraph

logger = logging.getLogger(__name__)

PREFIX = "aaspect-"
# Neo4j's rule for database names, lower case only. DROP DATABASE takes no parameter, so
# a name reaches the query text, and only a name matching this may.
_DATABASE_NAME = re.compile(r"[a-z][a-z0-9.-]{2,62}")
_ONLINE_POLL_SECONDS = 0.2


class DozerDbStore:
    """One database per analysis, on a Neo4j server with the DozerDB plugin."""

    def __init__(
        self, uri: str, user: str, password: str, online_timeout_seconds: float = 30
    ) -> None:
        self._uri, self._user, self._password = uri, user, password
        self._online_timeout = online_timeout_seconds
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    @contextmanager
    def open(self) -> Generator[Neo4aasGraph]:
        # Fails at once; the first query would retry for about 30 s if the server is down.
        self._driver.verify_connectivity()
        name = _checked(PREFIX + uuid.uuid4().hex)
        self._system("CREATE DATABASE $name NOWAIT", name=name)
        try:
            self._wait_until_online(name)
            client = AASNeo4JClient(
                self._uri, self._user, self._password, model_config=MODEL_CONFIG, database=name
            )
            try:
                yield Neo4aasGraph(client)
            finally:
                client.driver.close()
        finally:
            self._drop(name)

    def drop_leftovers(self) -> None:
        """Drop the databases of analyses that a crash or restart cut short."""
        try:
            records = self._system(
                "SHOW DATABASES YIELD name WHERE name STARTS WITH $prefix RETURN name",
                prefix=PREFIX,
            )
        except Exception:
            # The server may start after AASpect; analyses then fail until it is up.
            logger.warning("Graph database not reachable", exc_info=True)
            return
        for record in records:
            self._drop(record["name"])

    def _wait_until_online(self, name: str) -> None:
        # DozerDB rejects CREATE DATABASE ... WAIT.
        deadline = time.monotonic() + self._online_timeout
        while True:
            records = self._system(
                "SHOW DATABASES YIELD name, currentStatus WHERE name = $name RETURN currentStatus",
                name=name,
            )
            if any(record["currentStatus"] == "online" for record in records):
                return
            if time.monotonic() > deadline:
                raise TimeoutError(f"database {name} did not come online")
            time.sleep(_ONLINE_POLL_SECONDS)

    def _drop(self, name: str) -> None:
        try:
            query = f"DROP DATABASE `{_checked(name)}`"  # arch-allow: name passed _checked
            self._system(cast(LiteralString, query))
        except Exception:
            # The next startup drops it with the other leftovers.
            logger.warning("Could not drop database %s", name, exc_info=True)

    def _system(self, query: LiteralString, **parameters: str) -> list[Record]:
        records, _, _ = self._driver.execute_query(query, parameters, database_="system")
        return records


def _checked(name: str) -> str:
    if not _DATABASE_NAME.fullmatch(name):
        raise ValueError(f"not a valid database name: {name!r}")
    return name
