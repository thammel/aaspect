"""End-to-end smoke test: real adapters wired by main, driven through HTTP."""

import json
import unittest
from contextlib import ExitStack
from dataclasses import replace

from fastapi.testclient import TestClient

from aaspect.config.settings import Settings
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.main import build_app
from tests.adapters.files.packages import aasx
from tests.adapters.schema.samples import sample

V3_0, V3_2 = MetamodelVersion.V3_0, MetamodelVersion.V3_2


class TestEndToEnd(unittest.TestCase):
    def test_upload_to_report(self) -> None:
        broken = json.loads(sample(V3_2, "submodel.json"))
        del broken["submodels"][0]["id"]
        files = [
            ("files", ("shell.json", sample(V3_2, "shell.json"))),
            ("files", ("broken.json", json.dumps(broken).encode())),
            ("files", ("package.aasx", aasx({"/aasx/data.xml": sample(V3_0, "submodel.xml")}))),
            ("files", ("notes.txt", b"hello")),
        ]
        settings = replace(Settings(), validation_workers=2)
        with ExitStack() as resources:
            client = TestClient(build_app(settings, resources))
            response = client.post("/analyses", files=files, data={"version": "auto"})
            self.assertEqual(response.status_code, 200)
            self.assertIn("Version per file", response.text)
            report = json.loads(client.get(str(response.url) + "/report.json").content)

        [section] = report["sections"]
        self.assertEqual(section["status"], "completed")
        blocks = {block.get("title") or block["rule_id"]: block for block in section["blocks"]}
        self.assertEqual(
            blocks["Version per file"]["rows"],
            [
                [
                    "shell.json",
                    "3.2",
                    "auto: newest valid version, older versions not checked",
                    "yes",
                ],
                ["broken.json", "3.2", "auto: no version valid, fewest violations", "no"],
                ["package.aasx:/aasx/data.xml", "3.0", "XML namespace", "yes"],
            ],
        )
        self.assertEqual(blocks["unreadable-file"]["locations"][0]["file"], "notes.txt")
        self.assertEqual(blocks["required"]["locations"][0]["file"], "broken.json")


if __name__ == "__main__":
    unittest.main()
