import hashlib
import json
import time
import unittest

from aaspect.adapters.templates import idta
from aaspect.adapters.templates.idta import IdtaTemplates
from aaspect.domain.report import ShownError
from aaspect.domain.templates.catalogue import Tier

_CONTENT = json.dumps(
    {"submodels": [{"id": "urn:t", "semanticId": {"keys": [{"value": "urn:nameplate"}]}}]}
).encode()


def _manifest(content: bytes = _CONTENT) -> dict:
    return {
        "repository": "owner/repo",
        "commit": "abc",
        "files": [
            {
                "path": "published/Name plate/1/0/IDTA 1-0_Template.json",
                "priority": 0,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "tier": "current",
                "version": [1, 0],
            }
        ],
    }


class TestIdtaTemplates(unittest.TestCase):
    def test_downloads_the_pinned_files_and_compiles_them(self) -> None:
        fetched: list[tuple[str, int]] = []

        def fetch(url: str, size: int, deadline: float) -> bytes:
            fetched.append((url, size))
            return _CONTENT

        source = IdtaTemplates("https://mirror/", fetch, _manifest())
        self.assertTrue(source.load())
        template = source.catalogue().lookup("urn:nameplate")
        assert template is not None
        self.assertEqual((template.name, template.tier), ("IDTA 1-0_Template (1.0)", Tier.CURRENT))
        self.assertEqual(
            fetched,
            [
                (
                    "https://mirror/owner/repo/abc/published/Name%20plate/1/0/IDTA%201-0_Template.json",
                    len(_CONTENT),
                )
            ],
        )

    def test_unavailable_until_loaded_without_waiting(self) -> None:
        source = IdtaTemplates(fetch=lambda *_: _CONTENT, manifest=_manifest())
        with self.assertRaises(ShownError):
            source.catalogue()

    def test_changed_content_is_refused(self) -> None:
        source = IdtaTemplates(fetch=lambda *_: b'{"submodels": []}', manifest=_manifest())
        with self.assertLogs("aaspect.adapters.templates.idta", "WARNING"):
            self.assertFalse(source.load())
        with self.assertRaises(ShownError):
            source.catalogue()

    def test_start_retries_in_the_background(self) -> None:
        answers = iter([OSError("offline"), _CONTENT])

        def fetch(url: str, size: int, deadline: float) -> bytes:
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer

        source = IdtaTemplates(fetch=fetch, manifest=_manifest(), retry_seconds=0.01)
        with self.assertLogs("aaspect.adapters.templates.idta", "WARNING"):
            source.start()
            for _ in range(500):
                try:
                    source.catalogue()
                    break
                except ShownError:
                    time.sleep(0.01)
        self.assertEqual(len(source.catalogue()), 1)

    def test_only_https_addresses(self) -> None:
        for url in ("http://mirror", "file:///etc", "ftp://mirror"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                IdtaTemplates(url, manifest=_manifest())

    def test_the_shipped_manifest_lists_only_paths_sizes_and_hashes(self) -> None:
        manifest = IdtaTemplates()._manifest
        self.assertEqual(manifest["repository"], "admin-shell-io/submodel-templates")
        self.assertTrue(manifest["files"])
        for entry in manifest["files"]:
            self.assertEqual(
                set(entry),
                {"path", "sha", "sha256", "size", "family", "priority", "version", "tier"},
            )
            self.assertIn(entry["tier"], ("current", "superseded", "withdrawn"))


class TestFetch(unittest.TestCase):
    def test_refuses_other_schemes_and_redirects(self) -> None:
        handlers = {type(handler).__name__ for handler in vars(idta._OPENER)["handlers"]}
        self.assertNotIn("FileHandler", handlers)
        self.assertNotIn("FTPHandler", handlers)
        self.assertNotIn("HTTPRedirectHandler", handlers)
        self.assertIn("_NoRedirects", handlers)


if __name__ == "__main__":
    unittest.main()
