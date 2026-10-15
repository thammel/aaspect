import unittest

from aaspect.domain.blocks import Location, Severity
from aaspect.domain.constraints.findings import violation_findings
from aaspect.domain.constraints.violations import ConstraintViolation, Place
from aaspect.domain.id_collisions import Occurrence

OCCURRENCES = {
    ("sm", 0): Occurrence("sm", "sm", "Submodel", 1, 0, "a.json"),
    ("shared", 0): Occurrence("shared", "shared", "Submodel", 300, 0, "b.json"),
    ("shared", 1): Occurrence("shared__collision-1", "shared", "Submodel", 1, 1, "z.json"),
}


def _violation(rule: str, message: str, *places: Place, more: bool = False):
    return ConstraintViolation(rule, message, places, more)


class TestViolationFindings(unittest.TestCase):
    def test_groups_by_rule_and_message(self) -> None:
        findings = violation_findings(
            [
                _violation("AASd-002", "bad 'x'", Place("sm", 0, "a")),
                _violation("AASd-002", "bad 'x'", Place("sm", 0, "b")),
                _violation("AASd-002", "bad 'y'", Place("sm", 0, "c")),
                _violation("AASd-005", "no version", Place("sm", 0, "")),
            ],
            OCCURRENCES,
        )
        self.assertEqual(
            [(f.rule_id, f.message, len(f.locations)) for f in findings],
            [("AASd-002", "bad 'x'", 2), ("AASd-002", "bad 'y'", 1), ("AASd-005", "no version", 1)],
        )
        self.assertEqual(findings[0].severity, Severity.ERROR)
        self.assertEqual(findings[2].locations, (Location("a.json", "sm", None),))

    def test_shared_object_is_listed_once_with_its_file_count(self) -> None:
        [finding] = violation_findings(
            [_violation("AASd-117", "no idShort", Place("shared", 0, "p"), Place("sm", 0, "q"))],
            OCCURRENCES,
        )
        self.assertEqual(
            finding.locations,
            (Location("b.json", "shared", "p"), Location("a.json", "sm", "q")),
        )
        self.assertIn("Found in 2 objects that occur in 301 files", finding.message)

    def test_collision_variant_names_its_own_file(self) -> None:
        [finding] = violation_findings(
            [_violation("AASd-117", "m", Place("shared", 1, "p"))], OCCURRENCES
        )
        self.assertEqual(finding.locations, (Location("z.json", "shared", "p"),))
        self.assertEqual(finding.message, "m")

    def test_unplaced_and_capped_violations(self) -> None:
        [finding] = violation_findings(
            [
                _violation("AASd-121", "m", more=True),
                _violation("AASd-121", "m", Place("gone", 0, "")),
            ],
            OCCURRENCES,
        )
        self.assertEqual(finding.locations, (Location(None, "gone", None),))
        self.assertTrue(finding.message.endswith("Shared by more objects than listed."))


if __name__ == "__main__":
    unittest.main()
