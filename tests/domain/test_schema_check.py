import unittest

from aaspect.domain.blocks import Location, Severity
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.schema_check import SchemaViolation, group_violations

V3_2 = MetamodelVersion.V3_2
V3_0 = MetamodelVersion.V3_0


def _violation(keyword: str, schema_path: str, instance_path: str = "/x", message: str = "m"):
    return SchemaViolation(keyword, schema_path, instance_path, message)


class TestGroupViolations(unittest.TestCase):
    def test_groups_by_rule_not_message(self) -> None:
        first = _violation("required", "/$defs/Property/required", "/a", "'{huge element}' is bad")
        second = _violation("required", "/$defs/Property/required", "/b", "'{other}' is bad")
        [finding] = group_violations([("a.json", V3_2, [first]), ("b.json", V3_2, [second])])
        self.assertEqual(finding.rule_id, "required")
        self.assertEqual(finding.severity, Severity.ERROR)
        self.assertEqual(
            finding.locations,
            (
                Location(file="a.json", element_path="/a"),
                Location(file="b.json", element_path="/b"),
            ),
        )
        self.assertIn("/$defs/Property/required", finding.message)
        self.assertIn("'{huge element}' is bad", finding.message)

    def test_separates_versions_and_schema_paths(self) -> None:
        violation = _violation("required", "/p")
        findings = group_violations(
            [
                ("a.json", V3_2, [violation, _violation("required", "/q")]),
                ("b.json", V3_0, [violation]),
            ]
        )
        self.assertEqual(len(findings), 3)

    def test_most_frequent_first(self) -> None:
        rare = _violation("pattern", "/rare")
        common = _violation("type", "/common")
        findings = group_violations([("a.json", V3_2, [rare, common, common])])
        self.assertEqual([finding.rule_id for finding in findings], ["type", "pattern"])

    def test_no_violations_no_findings(self) -> None:
        self.assertEqual(group_violations([("a.json", V3_2, [])]), ())


if __name__ == "__main__":
    unittest.main()
