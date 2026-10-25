import unittest

from aaspect.adapters.web.views import finding_groups, is_distribution
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


if __name__ == "__main__":
    unittest.main()
