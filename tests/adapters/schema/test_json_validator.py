import json
import unittest

from aaspect.adapters.schema.json_validator import JsonSchemaValidator
from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.schema_check import SchemaViolation
from tests.adapters.schema.samples import official_validator, sample

V3_0, V3_1, V3_2 = MetamodelVersion.V3_0, MetamodelVersion.V3_1, MetamodelVersion.V3_2


def _validate(content: bytes, version: MetamodelVersion = V3_2) -> list[SchemaViolation]:
    document = AasDocument("a.json", DocumentFormat.JSON, content)
    return list(official_validator().validate(document, version))


def _with_description(text: str) -> bytes:
    document = json.loads(sample(V3_2, "submodel.json"))
    document["submodels"][0]["description"] = [{"language": "en", "text": text}]
    return json.dumps(document).encode()


class TestOfficialSamples(unittest.TestCase):
    def test_samples_valid_under_own_version(self) -> None:
        for version in MetamodelVersion:
            for name in ("shell.json", "submodel.json"):
                with self.subTest(version=version, name=name):
                    self.assertEqual(_validate(sample(version, name), version), [])

    def test_newest_sample_invalid_under_older_versions(self) -> None:
        for version in (V3_0, V3_1):
            with self.subTest(version=version):
                self.assertNotEqual(_validate(sample(V3_2, "submodel.json"), version), [])


class TestViolations(unittest.TestCase):
    def test_missing_required_property(self) -> None:
        document = json.loads(sample(V3_2, "submodel.json"))
        del document["submodels"][0]["id"]
        [violation] = _validate(json.dumps(document).encode())
        self.assertEqual(violation.keyword, "required")
        self.assertEqual(violation.schema_path, "/definitions/Identifiable/allOf/1/required")
        self.assertEqual(violation.instance_path, "/submodels/0")

    def test_long_message_is_truncated(self) -> None:
        # Stays under the 1023-character limit, so the pattern is the only violation.
        [violation] = _validate(_with_description("\x01" + "a" * 1000))
        self.assertLessEqual(len(violation.message), 300)
        self.assertTrue(violation.message.endswith("…"))


class TestCharacters(unittest.TestCase):
    def test_characters_outside_bmp_are_valid(self) -> None:
        for text in ("Grüße 😀", "𠀀 CJK Extension B", "tab\tand\nnewline"):
            with self.subTest(text=text):
                self.assertEqual(_validate(_with_description(text)), [])

    def test_control_character_violates_pattern(self) -> None:
        [violation] = _validate(_with_description("bell\x07"))
        self.assertEqual(violation.keyword, "pattern")
        self.assertEqual(violation.instance_path, "/submodels/0/description/0/text")

    def test_lone_surrogate_is_a_violation_not_a_crash(self) -> None:
        content = _with_description("x").replace(b'"text": "x"', b'"text": "\\ud800"')
        [violation] = _validate(content)
        self.assertEqual(violation.keyword, "lone-surrogate")


class TestMalformedInput(unittest.TestCase):
    def test_not_json(self) -> None:
        for content in (b"", b"{", b"\xff\xfe\x00", b"[" * 100_000):
            with self.subTest(content=content[:10]):
                [violation] = _validate(content)
                self.assertEqual(violation.keyword, "well-formedness")

    def test_byte_order_mark_is_accepted(self) -> None:
        self.assertEqual(_validate(b"\xef\xbb\xbf" + sample(V3_2, "submodel.json")), [])


class TestPatternRewrite(unittest.TestCase):
    def test_unknown_surrogate_form_fails_loudly(self) -> None:
        # Built from pieces so no tool turns the escaped pair into a literal emoji.
        pair = "\\u" + "d83d" + "\\u" + "de00"
        with self.assertRaises(ValueError):
            JsonSchemaValidator({"type": "string", "pattern": f"^{pair}$"})

    def test_rewrite_reaches_nested_patterns(self) -> None:
        pairs = r"\ud800[\udc00-\udfff]|[\ud801-\udbfe][\udc00-\udfff]|\udbff[\udc00-\udfff]"
        schema = {"type": "array", "items": {"type": "string", "pattern": f"^({pairs})*$"}}
        validator = JsonSchemaValidator(schema)
        self.assertEqual(validator.validate(json.dumps(["😀"]).encode()), [])


if __name__ == "__main__":
    unittest.main()
