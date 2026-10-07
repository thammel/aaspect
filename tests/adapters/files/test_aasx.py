import unittest
import zipfile

from aaspect.adapters.files.aasx import aas_parts
from aaspect.adapters.files.sniff import Unreadable
from tests.adapters.files.packages import LIMITS, ORIGIN, SPEC, aasx, rels, zip_bytes

XML = b'<environment xmlns="https://admin-shell.io/aas/3/2"/>'
DOCX_MAIN = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"


class TestFindParts(unittest.TestCase):
    def test_follows_relationships(self) -> None:
        package = aasx({"/aasx/data.xml": XML, "/aasx/more.json": b"{}"})
        self.assertEqual(
            aas_parts(package, LIMITS), [("/aasx/data.xml", XML), ("/aasx/more.json", b"{}")]
        )

    def test_relative_encoded_and_case_insensitive_targets(self) -> None:
        package = aasx({"/aasx/My Data.xml": XML}, spec_targets=["My%20DATA.xml"])
        [(part, content)] = aas_parts(package, LIMITS)
        self.assertEqual((part, content), ("/aasx/My DATA.xml", XML))

    def test_accepts_legacy_relationship_types(self) -> None:
        package = zip_bytes(
            {
                "_rels/.rels": rels((ORIGIN.replace("://", "://www."), "/aasx/aasx-origin")),
                "aasx/_rels/aasx-origin.rels": rels((SPEC.replace("://", "://www."), "d.xml")),
                "aasx/d.xml": XML,
            }
        )
        self.assertEqual(len(aas_parts(package, LIMITS)), 1)

    def test_ignores_supplementary_files(self) -> None:
        package = aasx({"/aasx/data.xml": XML, "/aasx/files/manual.pdf": b"%PDF"}, ["data.xml"])
        self.assertEqual([part for part, _ in aas_parts(package, LIMITS)], ["/aasx/data.xml"])


class TestNotAnAasx(unittest.TestCase):
    def test_rejected_packages(self) -> None:
        cases = {
            "office document": zip_bytes(
                {
                    "_rels/.rels": rels((DOCX_MAIN, "word/document.xml")),
                    "word/document.xml": b"<w:document/>",
                }
            ),
            "no aas-spec": aasx({}),
            "missing part": aasx({}, spec_targets=["gone.xml"]),
            "broken rels": zip_bytes({"_rels/.rels": b"<Relationships"}),
            "truncated": aasx({"/aasx/data.xml": XML})[:200],
            "garbage after magic": b"PK\x03\x04" + b"\x00" * 100,
        }
        for name, package in cases.items():
            with self.subTest(name), self.assertRaises(Unreadable):
                aas_parts(package, LIMITS)


class TestHostilePackages(unittest.TestCase):
    def test_zip_bomb_part_over_size_limit(self) -> None:
        package = aasx({"/aasx/data.xml": b"<" + b" " * 2_000_000})
        with self.assertRaisesRegex(Unreadable, "larger than"):
            aas_parts(package, LIMITS)

    def test_zip_bomb_by_compression_ratio(self) -> None:
        package = aasx({"/aasx/data.xml": b"<" + b" " * 900_000})
        with self.assertRaisesRegex(Unreadable, "compressed suspiciously"):
            aas_parts(package, LIMITS)

    def test_too_many_entries(self) -> None:
        entries = {f"aasx/files/{i}.bin": b"" for i in range(LIMITS.max_entries + 1)}
        with self.assertRaisesRegex(Unreadable, "more than"):
            aas_parts(zip_bytes(entries), LIMITS)

    def test_target_outside_package(self) -> None:
        for target in ("../../etc/passwd", "/../secret.xml", "a/../../../x.xml"):
            package = aasx({"/aasx/data.xml": XML}, spec_targets=[target])
            with self.subTest(target), self.assertRaisesRegex(Unreadable, "outside"):
                aas_parts(package, LIMITS)

    def test_traversal_entry_names_are_only_names(self) -> None:
        package = aasx({"../../evil.xml": XML, "/aasx/data.xml": XML}, ["data.xml"])
        self.assertEqual([part for part, _ in aas_parts(package, LIMITS)], ["/aasx/data.xml"])

    def test_duplicate_entry_names(self) -> None:
        package = zip_bytes({"aasx/data.xml": XML, "aasx/DATA.xml": XML})
        with self.assertRaisesRegex(Unreadable, "two entries"):
            aas_parts(package, LIMITS)

    def test_external_entity_in_relationships(self) -> None:
        bad_rels = (
            b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Type="' + ORIGIN.encode() + b'" Target="&x;" Id="r"/></Relationships>'
        )
        package = zip_bytes({"_rels/.rels": bad_rels})
        with self.assertRaises(Unreadable) as raised:
            aas_parts(package, LIMITS)
        self.assertNotIn("root:", str(raised.exception))

    def test_unsupported_compression(self) -> None:
        package = bytearray(aasx({"/aasx/data.xml": XML}))
        # Patch the compression method of every entry to an unknown value.
        for offset in range(len(package) - 4):
            if package[offset : offset + 4] in (b"PK\x03\x04", b"PK\x01\x02"):
                field = offset + (8 if package[offset + 2] == 3 else 10)
                package[field : field + 2] = (99).to_bytes(2, "little")
        with self.assertRaises(Unreadable):
            aas_parts(bytes(package), LIMITS)


class TestArchiveIsNeverExtracted(unittest.TestCase):
    def test_no_extract_calls(self) -> None:
        original = zipfile.ZipFile.extract, zipfile.ZipFile.extractall

        def forbidden(*args: object, **kwargs: object) -> None:
            raise AssertionError("archive must not be extracted")

        zipfile.ZipFile.extract = forbidden  # type: ignore[method-assign]
        zipfile.ZipFile.extractall = forbidden  # type: ignore[method-assign]
        try:
            aas_parts(aasx({"/aasx/data.xml": XML}), LIMITS)
        finally:
            zipfile.ZipFile.extract, zipfile.ZipFile.extractall = original


if __name__ == "__main__":
    unittest.main()
