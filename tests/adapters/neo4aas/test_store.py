import os
import time
import unittest

from neo4j.exceptions import ServiceUnavailable

from aaspect.adapters.neo4aas.store import PREFIX, DozerDbStore, _checked

_URI = os.environ.get("AASPECT_TEST_NEO4J_URI")
_PASSWORD = os.environ.get("AASPECT_TEST_NEO4J_PASSWORD", "")


class TestDatabaseName(unittest.TestCase):
    def test_generated_names_pass(self) -> None:
        self.assertEqual(_checked("aaspect-0f3a9c"), "aaspect-0f3a9c")

    def test_names_that_could_break_out_of_the_query_are_refused(self) -> None:
        for name in ("aaspect-`x", "aaspect x", "Aaspect-1", "-aaspect", "ab", "a" * 64):
            with self.subTest(name=name), self.assertRaises(ValueError):
                _checked(name)


class TestUnreachableServer(unittest.TestCase):
    def test_open_fails_without_waiting_for_retries(self) -> None:
        # Nothing listens on port 9 (the old discard service) on a normal machine.
        store = DozerDbStore("bolt://127.0.0.1:9", "neo4j", "unused")
        self.addCleanup(store.close)
        started = time.monotonic()
        with self.assertRaises(ServiceUnavailable), store.open():
            pass
        self.assertLess(time.monotonic() - started, 5)


@unittest.skipUnless(_URI, "set AASPECT_TEST_NEO4J_URI to run against a DozerDB server")
class TestDozerDbStore(unittest.TestCase):
    def setUp(self) -> None:
        assert _URI
        self.store = DozerDbStore(_URI, "neo4j", _PASSWORD)
        self.addCleanup(self.store.close)

    def _databases(self) -> set[str]:
        records = self.store._system(
            "SHOW DATABASES YIELD name WHERE name STARTS WITH $prefix RETURN name", prefix=PREFIX
        )
        return {record["name"] for record in records}

    def test_database_exists_only_while_open(self) -> None:
        before = self._databases()
        with self.store.open() as graph:
            graph.upload([{"submodels": [{"id": "urn:x", "modelType": "Submodel"}]}])
            graph.link_references()
            during = self._databases() - before
        self.assertEqual(len(during), 1)
        self.assertEqual(self._databases(), before)

    def test_leftovers_are_dropped(self) -> None:
        self.store._system("CREATE DATABASE $name", name=PREFIX + "leftover")

        self.store.drop_leftovers()

        self.assertEqual(self._databases(), set())


if __name__ == "__main__":
    unittest.main()
