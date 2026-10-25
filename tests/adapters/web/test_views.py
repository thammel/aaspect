import unittest

from aaspect.adapters.web.views import chart_kind, finding_groups, is_distribution, number
from aaspect.domain.blocks import Finding, Location, Severity, Table


def _finding(rule: str, severity: Severity, places: int) -> Finding:
    return Finding(rule, severity, "m", tuple(Location(file="a") for _ in range(places)))


class TestViews(unittest.TestCase):
    def test_groups_put_errors_first_then_most_places(self) -> None:
        blocks = (
            Table("t", ("A",), ()),
            _finding("id-collision", Severity.WARNING, 9),
            _finding("pattern", Severity.ERROR, 1),
            _finding("id-collision", Severity.WARNING, 2),
            _finding("minLength", Severity.ERROR, 3),
        )
        groups = finding_groups(blocks)
        self.assertEqual([g.rule_id for g in groups], ["minLength", "pattern", "id-collision"])
        self.assertEqual((len(groups[2].findings), groups[2].places), (2, 11))

    def test_same_rule_with_two_severities_stays_apart(self) -> None:
        groups = finding_groups((_finding("r", Severity.ERROR, 1), _finding("r", Severity.INFO, 1)))
        self.assertEqual(len(groups), 2)

    def test_only_tables_ending_in_a_share_are_distributions(self) -> None:
        self.assertTrue(is_distribution(Table("t", ("Value", "Count", "Share (%)"), ())))
        self.assertFalse(is_distribution(Table("t", ("Value", "Count"), ())))
        self.assertFalse(is_distribution(_finding("r", Severity.INFO, 0)))
        self.assertFalse(is_distribution(Table("t", ("Value", "Share (%)"), (("a", "n/a"),))))

    def test_chart_kind_follows_the_table_shape(self) -> None:
        share = ("Value", "Count", "Share (%)")
        cases = [
            (Table("t", ("A",), ()), "empty"),
            (Table("t", ("A", "B"), (("x", 1),)), "figures"),
            (Table("t", ("Object", "Count"), (("a", 1), ("b", 2))), "tiles"),
            (
                Table(
                    "t",
                    ("M", "Count", "Min", "Max", "Mean", "Median"),
                    (("d", 1, 1, 2, 1.5, 1),) * 2,
                ),
                "table",
            ),
            (Table("t", share, (("a", 1, 50.0), ("b", 1, 50.0))), "stack"),
            (Table("t", share, tuple((str(i), 1, 20.0) for i in range(5))), "bars"),
            (
                Table("t", ("O", "A", "Filled", "Of", "Share (%)"), (("o", "a", 1, 2, 50.0),) * 2),
                "filled",
            ),
            (Table("t", ("File", "Version"), (("a", "3.0"), ("b", "3.1"))), "table"),
            (
                Table(
                    "t", ("Template", "Source", "Submodels", "Conformant"), (("n", "s", 2, 1),) * 2
                ),
                "scoreboard",
            ),
            (Table("t", ("Template", "A", "B", "C"), (("n", 1, 0, 3), ("m", 0, 2, 0))), "matrix"),
        ]
        for table, kind in cases:
            with self.subTest(table.columns):
                self.assertEqual(chart_kind(table), kind)

    def test_whole_numbers_get_separators(self) -> None:
        self.assertEqual(
            [number(72110), number(3.26), number("1000"), number(True)],
            ["72,110", 3.26, "1000", True],
        )


if __name__ == "__main__":
    unittest.main()
