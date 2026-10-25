import unittest

from aaspect.domain.blocks import Finding, Location, Severity, Table
from aaspect.domain.per_file import Owners, file_sections
from aaspect.domain.report import Report, Section, SectionStatus


class TestOwners(unittest.TestCase):
    def test_package_parts_and_colons_in_upload_names(self) -> None:
        owners = Owners(("a.json", "b.aasx", "c:d.aasx"))
        labels = ["a.json", "b.aasx:/aasx/x.json", "c:d.aasx:/p", "elsewhere:/p", None]
        self.assertEqual(
            [owners.of(label) for label in labels], ["a.json", "b.aasx", "c:d.aasx", None, None]
        )


class TestFileSections(unittest.TestCase):
    def test_keeps_only_what_names_the_file(self) -> None:
        schema = Section(
            "schema",
            "Schema check",
            SectionStatus.COMPLETED,
            (
                Table("Versions", ("Version", "Documents"), (("3.0", 2),)),
                Table(
                    "Version per file",
                    ("File", "Version"),
                    (("a.json", "3.0"), ("b.aasx:/x", "3.1")),
                ),
                Finding(
                    "pattern", Severity.ERROR, "m", (Location("a.json"), Location("b.aasx:/x"))
                ),
                Finding("minLength", Severity.ERROR, "m", (Location("a.json"),)),
            ),
        )
        failed = Section("constraints", "Constraints", SectionStatus.FAILED, reason="down")
        report = Report("0.1.0", ("a.json", "b.aasx"), (schema, failed))

        narrowed, other = file_sections(report, "b.aasx")

        per_file, finding = narrowed.blocks
        assert isinstance(per_file, Table) and isinstance(finding, Finding)
        self.assertEqual(per_file.rows, (("b.aasx:/x", "3.1"),))
        self.assertEqual(
            (finding.rule_id, finding.locations), ("pattern", (Location("b.aasx:/x"),))
        )
        self.assertEqual(
            (other.status, other.reason, other.blocks), (SectionStatus.FAILED, "down", ())
        )

    def test_a_column_naming_only_this_file_drops_out(self) -> None:
        table = Table("Version per file", ("File", "Version"), (("a.json", "3.0"),))
        section = Section("schema", "Schema check", SectionStatus.COMPLETED, (table,))
        [narrowed] = file_sections(Report("0.1.0", ("a.json",), (section,)), "a.json")
        [kept] = narrowed.blocks
        assert isinstance(kept, Table)
        self.assertEqual((kept.columns, kept.rows), (("Version",), (("3.0",),)))


if __name__ == "__main__":
    unittest.main()
