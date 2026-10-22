import unittest

from aaspect.domain.templates.check import Deviation, DeviationKind, deviations
from aaspect.domain.templates.elements import (
    Cardinality,
    Element,
    id_short_matches,
    matching_key,
)

ONE = Cardinality(1, 1)
OPTIONAL = Cardinality(0, 1)
MANY = Cardinality(0, None)


def _property(id_short: str, semantic_id: str | None, **kwargs: object) -> Element:
    return Element(id_short, semantic_id, "Property", "xs:string", **kwargs)  # type: ignore[arg-type]


class TestMatching(unittest.TestCase):
    def test_key_drops_whitespace_and_irdi_version(self) -> None:
        self.assertEqual(matching_key(" 0173-1#02-AAO677#002 "), "0173-1#02-AAO677")
        self.assertEqual(matching_key("https://x/1/0"), "https://x/1/0")
        self.assertIsNone(matching_key("   "))

    def test_id_short_placeholders_and_numbering(self) -> None:
        cases = [
            ("Document{00}", "Document01", True),
            ("Document__00__", "Document12", True),
            ("Doc{00}Part{00}", "Doc1Part2", True),
            ("ProductImage", "ProductImage01", True),
            ("ProductImage", "ProductImageX", False),
            ("Name", "Other", False),
            (None, None, True),
        ]
        for template, instance, expected in cases:
            with self.subTest(template=template, instance=instance):
                self.assertEqual(id_short_matches(template, instance), expected)


class TestDeviations(unittest.TestCase):
    def test_conformant_submodel_has_none(self) -> None:
        template = (_property("Name", "0173-1#02-A#001", cardinality=ONE),)
        self.assertEqual(deviations(template, (_property("Name", "0173-1#02-A#001"),)), [])

    def test_missing_and_too_many(self) -> None:
        template = (
            _property("Name", "urn:name", cardinality=ONE),
            _property("Note", "urn:note", cardinality=OPTIONAL),
        )
        submodel = (_property("Note", "urn:note"), _property("Note", "urn:note"))
        self.assertEqual(
            deviations(template, submodel),
            [
                Deviation(DeviationKind.MISSING, "Name", "1..1", "absent"),
                Deviation(DeviationKind.CARDINALITY, "Note", "0..1", "2"),
            ],
        )

    def test_types_version_id_short_and_unexpected(self) -> None:
        template = (
            _property("Name", "0173-1#02-A#001", cardinality=ONE),
            Element("Weight", "urn:w", "Property", "xs:double", cardinality=ONE),
        )
        submodel = (
            _property("Title", "0173-1#02-A#002"),
            Element("Weight", "urn:w", "MultiLanguageProperty", None),
            _property("Extra", "urn:extra"),
        )
        kinds = [(d.kind, d.path) for d in deviations(template, submodel)]
        self.assertEqual(
            kinds,
            [
                (DeviationKind.SEMANTIC_ID_VERSION, "Name"),
                (DeviationKind.ID_SHORT, "Name"),
                (DeviationKind.MODEL_TYPE, "Weight"),
                (DeviationKind.UNEXPECTED, "Extra"),
            ],
        )

    def test_value_type_compared_for_properties(self) -> None:
        template = (Element("D", "urn:d", "Property", "xs:date", cardinality=ONE),)
        found = deviations(template, (Element("D", "urn:d", "Property", "xs:string"),))
        self.assertEqual(found, [Deviation(DeviationKind.VALUE_TYPE, "D", "xs:date", "xs:string")])

    def test_children_of_collections_and_list_items(self) -> None:
        item = Element(
            None,
            "urn:doc",
            "SubmodelElementCollection",
            children=(_property("Title", "urn:title", cardinality=ONE),),
        )
        template = (
            Element(
                "Documents", "urn:docs", "SubmodelElementList", children=(item,), cardinality=ONE
            ),
        )
        submodel = (
            Element(
                "Documents",
                "urn:docs",
                "SubmodelElementList",
                children=(
                    Element(
                        None,
                        "urn:doc",
                        "SubmodelElementCollection",
                        children=(_property("Title", "urn:title"),),
                    ),
                    Element(None, "urn:doc", "SubmodelElementCollection"),
                ),
            ),
        )
        self.assertEqual(
            deviations(template, submodel),
            [Deviation(DeviationKind.MISSING, "Documents[1].Title", "1..1", "absent")],
        )

    def test_siblings_sharing_a_semantic_id_match_by_id_short(self) -> None:
        template = (
            _property("Phone", "urn:contact", cardinality=ONE),
            _property("Fax", "urn:contact", cardinality=OPTIONAL),
        )
        submodel = (_property("Phone", "urn:contact"),)
        self.assertEqual(deviations(template, submodel), [])

    def test_template_element_without_semantic_id_matches_by_id_short(self) -> None:
        template = (_property("Remark", None, cardinality=ONE),)
        self.assertEqual(
            deviations(template, ()),
            [Deviation(DeviationKind.MISSING, "Remark", "1..1", "absent")],
        )
        self.assertEqual(deviations(template, (_property("Remark", "urn:any"),)), [])

    def test_numbered_elements_count_against_cardinality(self) -> None:
        template = (_property("Marking{00}", "urn:marking", cardinality=Cardinality(1, None)),)
        submodel = (_property("Marking01", "urn:marking"), _property("Marking02", "urn:marking"))
        self.assertEqual(deviations(template, submodel), [])


if __name__ == "__main__":
    unittest.main()
