import json
import unittest
from collections.abc import Iterator, Sequence

from fastapi.testclient import TestClient

from aaspect.adapters.report_json.writer import JsonReportWriter
from aaspect.adapters.web.app import create_app
from aaspect.adapters.web.routes import WebLimits
from aaspect.domain.corpus import Upload
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Report
from tests.adapters.web.reports import XSS, full_report

LIMITS = WebLimits(
    max_upload_bytes=10_000, max_files=3, max_concurrent_analyses=1, max_stored_reports=2
)


class FakeAnalyse:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], MetamodelVersion | None]] = []

    def __call__(self, uploads: Sequence[Upload], version: MetamodelVersion | None) -> Report:
        self.calls.append(([upload.name for upload in uploads], version))
        return full_report()


def _files(*names: str, content: bytes = b"{}") -> list[tuple[str, tuple[str, bytes]]]:
    return [("files", (name, content)) for name in names]


class TestRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.analyse = FakeAnalyse()
        self.client = TestClient(create_app(self.analyse, JsonReportWriter(), LIMITS))

    def _upload(self, files: list, version: str = "auto"):
        return self.client.post(
            "/analyses", files=files, data={"version": version}, follow_redirects=False
        )

    def test_form_has_security_headers(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        policy = response.headers["content-security-policy"]
        self.assertIn("script-src 'self'", policy)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_upload_redirects_to_report_and_download(self) -> None:
        response = self._upload(_files("a.json", "a.json", "dir/b.xml"), "3.1")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            self.analyse.calls, [(["a.json", "a.json (2)", "dir/b.xml"], MetamodelVersion.V3_1)]
        )
        page = self.client.get(response.headers["location"])
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(XSS, page.text)
        download = self.client.get(response.headers["location"] + "/report.json")
        self.assertEqual(download.headers["content-type"], "application/json")
        self.assertIn("attachment", download.headers["content-disposition"])
        self.assertEqual(json.loads(download.content)["format_version"], "1")

    def test_auto_means_no_version(self) -> None:
        self._upload(_files("a.json"))
        self.assertIsNone(self.analyse.calls[0][1])

    def test_rejected_input(self) -> None:
        cases = {
            "unknown version": (_files("a.json"), "4.0"),
            "no files": ([], "auto"),
            "only empty files": (_files("a.json", content=b""), "auto"),
            "too many files": (_files("1", "2", "3", "4"), "auto"),
        }
        for name, (files, version) in cases.items():
            with self.subTest(name):
                response = self._upload(files, version)
                self.assertEqual(response.status_code, 400)
                self.assertIn("Error 400", response.text)
        self.assertEqual(self.analyse.calls, [])

    def test_too_large_by_declared_length(self) -> None:
        response = self._upload(_files("a.json", content=b"x" * 20_000))
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.analyse.calls, [])

    def test_too_large_without_declared_length(self) -> None:
        def chunks() -> Iterator[bytes]:
            for _ in range(30):
                yield b"x" * 1000

        response = self.client.post(
            "/analyses",
            content=chunks(),
            headers={"content-type": "multipart/form-data; boundary=b"},
        )
        self.assertEqual(response.status_code, 413)

    def test_unknown_report(self) -> None:
        for path in ("/reports/nope", "/reports/nope/report.json"):
            with self.subTest(path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_oldest_report_expires(self) -> None:
        locations = [self._upload(_files("a.json")).headers["location"] for _ in range(3)]
        self.assertEqual(self.client.get(locations[0]).status_code, 404)
        self.assertEqual(self.client.get(locations[2]).status_code, 200)

    def test_upload_script_is_served(self) -> None:
        response = self.client.get("/static/upload.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["content-type"])

    def test_no_api_docs(self) -> None:
        for path in ("/docs", "/openapi.json"):
            self.assertEqual(self.client.get(path).status_code, 404)


if __name__ == "__main__":
    unittest.main()
