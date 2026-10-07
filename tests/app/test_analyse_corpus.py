import unittest

from aaspect.app.analyse_corpus import AnalyseCorpus
from aaspect.domain.corpus import AasDocument, Corpus, DocumentFormat, Upload
from aaspect.domain.report import SectionStatus
from tests.app.fakes import BrokenValidator, FakeReader, FakeValidator

UPLOADS = (Upload("a.json", b"{}"), Upload("b.txt", b""))
CORPUS = Corpus((AasDocument("a.json", DocumentFormat.JSON, b"{}"),))


class TestAnalyseCorpus(unittest.TestCase):
    def test_report_lists_uploads_and_schema_section(self) -> None:
        report = AnalyseCorpus(FakeReader(CORPUS), FakeValidator({}), "0.1.0").run(UPLOADS, None)
        self.assertEqual(report.aaspect_version, "0.1.0")
        self.assertEqual(report.files, ("a.json", "b.txt"))
        [section] = report.sections
        self.assertEqual(section.status, SectionStatus.COMPLETED)

    def test_failing_analysis_gives_failed_section(self) -> None:
        report = AnalyseCorpus(FakeReader(CORPUS), BrokenValidator(), "0.1.0").run(UPLOADS, None)
        [section] = report.sections
        self.assertEqual(section.status, SectionStatus.FAILED)
        self.assertEqual(section.reason, "RuntimeError: schema failed to load")


if __name__ == "__main__":
    unittest.main()
