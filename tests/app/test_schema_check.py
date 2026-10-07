import unittest

from aaspect.app.schema_check import SECTION_KEY, check_schema
from aaspect.domain.blocks import Finding, Location, Table
from aaspect.domain.corpus import AasDocument, Corpus, DocumentFormat, ReadFailure
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import SectionStatus
from aaspect.domain.schema_check import SchemaViolation
from tests.app.fakes import FakeValidator

V3_0, V3_2 = MetamodelVersion.V3_0, MetamodelVersion.V3_2
VIOLATION = SchemaViolation("required", "/$defs/Property/required", "/submodels/0", "missing")


class TestCheckSchema(unittest.TestCase):
    def test_builds_tables_failures_and_findings(self) -> None:
        corpus = Corpus(
            documents=(
                AasDocument("a.json", DocumentFormat.JSON, b"{}"),
                AasDocument(
                    "p.aasx", DocumentFormat.XML, b"", part="/d.xml", declared_version=V3_0
                ),
            ),
            failures=(ReadFailure("broken.aasx", "not a ZIP archive"),),
        )
        validator = FakeValidator({("p.aasx:/d.xml", V3_0): [VIOLATION]})

        section = check_schema(corpus, validator, None)

        self.assertEqual((section.key, section.status), (SECTION_KEY, SectionStatus.COMPLETED))
        distribution, per_file, unreadable, violation = section.blocks
        assert isinstance(distribution, Table) and isinstance(per_file, Table)
        self.assertEqual(distribution.rows, (("3.2", 1), ("3.0", 1)))
        self.assertEqual([row[0] for row in per_file.rows], ["a.json", "p.aasx:/d.xml"])
        assert isinstance(unreadable, Finding) and isinstance(violation, Finding)
        self.assertEqual(unreadable.rule_id, "unreadable-file")
        self.assertEqual(unreadable.message, "not a ZIP archive")
        self.assertEqual(unreadable.locations, (Location(file="broken.aasx"),))
        self.assertEqual(
            violation.locations, (Location(file="p.aasx:/d.xml", element_path="/submodels/0"),)
        )

    def test_requested_version_applies_to_json(self) -> None:
        corpus = Corpus((AasDocument("a.json", DocumentFormat.JSON, b"{}"),))
        validator = FakeValidator({("a.json", V3_0): [VIOLATION]})

        section = check_schema(corpus, validator, V3_0)

        self.assertEqual(len(section.blocks), 3)

    def test_empty_corpus(self) -> None:
        section = check_schema(Corpus(()), FakeValidator({}), None)
        self.assertEqual(len(section.blocks), 2)


if __name__ == "__main__":
    unittest.main()
