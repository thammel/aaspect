import unittest

from aaspect.adapters.web.store import ReportStore
from aaspect.adapters.web.uploads import unique_names
from tests.adapters.web.reports import full_report


class TestUniqueNames(unittest.TestCase):
    def test_names(self) -> None:
        self.assertEqual(
            unique_names(
                ["a.json", "a.json", "a.json (2)", "C:\\x\\b.xml", "../../c", "", "y" * 300]
            ),
            ["a.json", "a.json (2)", "a.json (2) (2)", "b.xml", "c", "upload", "y" * 200],
        )


class TestReportStore(unittest.TestCase):
    def test_keys_are_unguessable_and_capacity_holds(self) -> None:
        store = ReportStore(capacity=2)
        keys = [store.add(full_report()) for _ in range(3)]
        self.assertEqual(len(set(keys)), 3)
        self.assertTrue(all(len(key) >= 32 for key in keys))
        self.assertIsNone(store.get(keys[0]))
        self.assertIsNotNone(store.get(keys[2]))


if __name__ == "__main__":
    unittest.main()
