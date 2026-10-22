import unittest

from aaspect.domain.blocks import Finding, Location, Severity
from aaspect.domain.templates.catalogue import Template, Tier
from aaspect.domain.templates.check import Deviation, DeviationKind
from aaspect.domain.templates.instances import CheckedSubmodel
from aaspect.domain.templates.report import deviation_findings, summary_table, template_table

_TEMPLATE = Template("Nameplate", Tier.CURRENT, "urn:nameplate", ())
_MISSING = Deviation(DeviationKind.MISSING, "Documents[0].Title", "1..1", "absent")
_NOTE = Deviation(DeviationKind.UNEXPECTED, "Extra", "not in the template", "Property")


def _checked(file: str, *found: Deviation) -> CheckedSubmodel:
    return CheckedSubmodel(_TEMPLATE, Location(file=file, identifiable_id="urn:sm"), found)


class TestTables(unittest.TestCase):
    def test_summary_and_per_template(self) -> None:
        checked = [_checked("a.json"), _checked("b.json", _MISSING, _NOTE)]
        summary = summary_table(5, checked, unchecked=1)
        self.assertEqual(summary.rows, ((5, 3, 2, 1, 1, 2),))
        self.assertEqual(
            template_table(checked).rows, (("Nameplate", "IDTA, current", 2, 1, 1, 1),)
        )


class TestFindings(unittest.TestCase):
    def test_grouped_without_list_positions_errors_first(self) -> None:
        other = Deviation(DeviationKind.MISSING, "Documents[3].Title", "1..1", "absent")
        checked = [_checked("a.json", _NOTE), _checked("b.json", _MISSING, other)]
        error, note = deviation_findings(checked)
        assert isinstance(error, Finding) and isinstance(note, Finding)
        self.assertEqual((error.rule_id, error.severity), ("template-missing", Severity.ERROR))
        self.assertIn("Documents[].Title", error.message)
        self.assertIn("1 submodel, 2 places", error.message)
        self.assertEqual(
            [place.element_path for place in error.locations],
            ["Documents[0].Title", "Documents[3].Title"],
        )
        self.assertEqual(note.severity, Severity.INFO)

    def test_values_from_files_are_shortened_and_made_visible(self) -> None:
        odd = Deviation(DeviationKind.UNEXPECTED, "x‮" + "y" * 500, "not in the template", "")
        [finding] = deviation_findings([_checked("a.json", odd)])
        assert isinstance(finding, Finding)
        self.assertIn("<U+202E>", finding.message)
        self.assertLess(len(finding.message), 700)


if __name__ == "__main__":
    unittest.main()
