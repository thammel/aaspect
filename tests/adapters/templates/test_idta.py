import json
import unittest

from aaspect.adapters.templates.idta import IdtaTemplates, _git_blob_sha
from aaspect.domain.report import ShownError
from aaspect.domain.templates.catalogue import Tier

_CONTENT = json.dumps({"submodels": []}).encode()


def _manifest(sha: str) -> dict:
    return {
        "repository": "owner/repo",
        "commit": "abc",
        "files": [
            {
                "path": "published/Name plate/1/0/IDTA 1-0_Template.json",
                "sha": sha,
                "tier": "current",
                "version": [1, 0],
            }
        ],
    }


class TestIdtaTemplates(unittest.TestCase):
    def test_downloads_the_pinned_files_once(self) -> None:
        fetched: list[str] = []

        def fetch(url: str) -> bytes:
            fetched.append(url)
            return _CONTENT

        source = IdtaTemplates("https://mirror/", fetch, _manifest(_git_blob_sha(_CONTENT)))
        [template_file] = source.templates()
        source.templates()
        self.assertEqual(
            fetched,
            ["https://mirror/owner/repo/abc/published/Name%20plate/1/0/IDTA%201-0_Template.json"],
        )
        self.assertEqual(
            (template_file.name, template_file.tier, template_file.version),
            ("IDTA 1-0_Template", Tier.CURRENT, (1, 0)),
        )

    def test_changed_content_is_refused_and_retried_later(self) -> None:
        calls = []

        def fetch(url: str) -> bytes:
            calls.append(url)
            return b'{"submodels": "changed"}'

        source = IdtaTemplates(
            fetch=fetch, manifest=_manifest(_git_blob_sha(_CONTENT)), retry_seconds=3600
        )
        with (
            self.assertLogs("aaspect.adapters.templates.idta", "WARNING"),
            self.assertRaises(ShownError),
        ):
            source.templates()
        with self.assertRaises(ShownError):
            source.templates()
        self.assertEqual(len(calls), 1)

    def test_retries_after_the_wait(self) -> None:
        answers = iter([OSError("offline"), _CONTENT])

        def fetch(url: str) -> bytes:
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer

        source = IdtaTemplates(
            fetch=fetch, manifest=_manifest(_git_blob_sha(_CONTENT)), retry_seconds=0
        )
        with (
            self.assertLogs("aaspect.adapters.templates.idta", "WARNING"),
            self.assertRaises(ShownError),
        ):
            source.templates()
        self.assertEqual(len(source.templates()), 1)

    def test_the_shipped_manifest_lists_only_paths_and_hashes(self) -> None:
        manifest = IdtaTemplates(fetch=lambda url: b"")._manifest
        self.assertEqual(manifest["repository"], "admin-shell-io/submodel-templates")
        self.assertTrue(manifest["files"])
        for entry in manifest["files"]:
            self.assertEqual(set(entry), {"path", "sha", "size", "family", "version", "tier"})
            self.assertIn(entry["tier"], ("current", "superseded", "withdrawn"))


if __name__ == "__main__":
    unittest.main()
