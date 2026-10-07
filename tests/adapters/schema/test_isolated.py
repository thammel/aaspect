import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from aaspect.adapters.schema.isolated import IsolatedSchemaValidator
from aaspect.adapters.schema.validator import OfficialSchemaValidator
from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import MetamodelVersion
from tests.adapters.schema.fake_validators import BrokenAtStartup, Misbehaving

V3_1, V3_2 = MetamodelVersion.V3_1, MetamodelVersion.V3_2


def _document(content: bytes, source: str = "a.json") -> AasDocument:
    return AasDocument(source, DocumentFormat.JSON, content)


class TestIsolatedSchemaValidator(unittest.TestCase):
    validator: IsolatedSchemaValidator

    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = IsolatedSchemaValidator(
            Misbehaving, workers=2, timeout_seconds=2, memory_bytes=1_000_000_000
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.validator.close()

    def _keywords(self, content: bytes) -> list[str]:
        return [v.keyword for v in self.validator.validate(_document(content), V3_2)]

    def test_passes_results_through(self) -> None:
        [violation] = self.validator.validate(_document(b"{}", "x.json"), V3_2)
        self.assertEqual(violation.message, "3.2:x.json")

    def test_timeout_becomes_violation_and_worker_is_replaced(self) -> None:
        started = time.perf_counter()
        [violation] = self.validator.validate(_document(b"slow"), V3_2)
        self.assertEqual((violation.keyword, violation.file_level), ("validation-timeout", True))
        self.assertLess(time.perf_counter() - started, 10)
        self.assertEqual(self._keywords(b"{}"), ["type"])

    def test_crash_becomes_violation(self) -> None:
        self.assertEqual(self._keywords(b"crash"), ["validation-aborted"])
        self.assertEqual(self._keywords(b"{}"), ["type"])

    def test_memory_limit(self) -> None:
        self.assertIn(self._keywords(b"hog")[0], {"validation-aborted", "validation-error"})
        self.assertEqual(self._keywords(b"{}"), ["type"])

    def test_exception_becomes_violation(self) -> None:
        [violation] = self.validator.validate(_document(b"raise"), V3_2)
        self.assertEqual(violation.keyword, "validation-error")
        self.assertIn("broken", violation.message)

    def test_concurrent_calls(self) -> None:
        documents = [_document(b"{}", f"{i}.json") for i in range(20)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda d: self.validator.validate(d, V3_2), documents))
        self.assertEqual([r[0].message for r in results], [f"3.2:{i}.json" for i in range(20)])

    def test_broken_schema_fails_at_construction(self) -> None:
        with self.assertRaises(ValueError):
            IsolatedSchemaValidator(BrokenAtStartup, 1, 1, 1_000_000_000)


class TestSlowPatternInXml(unittest.TestCase):
    def test_libxml2_pattern_blowup_is_stopped(self) -> None:
        # A file value of this length that fails the URI pattern keeps libxml2 busy for
        # about 30 s, growing about eightfold with each doubling of its length.
        value = "https://example.org/" + "a" * 1600 + " x"
        content = (
            '<environment xmlns="https://admin-shell.io/aas/3/1"><submodels><submodel>'
            "<id>s</id><submodelElements><file><idShort>f</idShort>"
            f"<value>{value}</value><contentType>application/pdf</contentType></file>"
            "</submodelElements></submodel></submodels></environment>"
        ).encode()
        document = AasDocument("x.xml", DocumentFormat.XML, content, declared_version=V3_1)
        validator = IsolatedSchemaValidator(
            OfficialSchemaValidator, workers=1, timeout_seconds=3, memory_bytes=2_000_000_000
        )
        try:
            started = time.perf_counter()
            [violation] = validator.validate(document, V3_1)
            self.assertEqual(violation.keyword, "validation-timeout")
            self.assertLess(time.perf_counter() - started, 15)
        finally:
            validator.close()


if __name__ == "__main__":
    unittest.main()
