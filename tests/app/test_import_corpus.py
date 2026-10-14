import unittest

from aaspect.app.import_corpus import ImportResult, import_corpus, import_section
from aaspect.domain.blocks import Finding, Location, Severity, Table
from aaspect.domain.corpus import AasDocument, DocumentFormat, ReadFailure
from aaspect.domain.id_collisions import Collision, Occurrence, Rename
from tests.app.graph_fakes import FakeParser, RecordingGraph


def _document(name: str) -> AasDocument:
    return AasDocument(name, DocumentFormat.JSON, b"")


def _submodels(*contents: tuple[str, str]) -> dict:
    return {"submodels": [{"id": i, "idShort": s} for i, s in contents]}


class TestImportCorpus(unittest.TestCase):
    def test_uploads_in_label_order_then_links_then_restores(self) -> None:
        parser = FakeParser({"a.json": _submodels(("x", "A")), "b.json": _submodels(("x", "B"))})
        graph = RecordingGraph()

        result = import_corpus([_document("b.json"), _document("a.json")], parser, graph)

        self.assertEqual(
            graph.calls,
            [
                ("upload", _submodels(("x", "A"))),
                ("upload", _submodels(("x__collision-1", "B"))),
                ("link", None),
                (
                    "occurrences",
                    (
                        Occurrence("x", "x", "Submodel", 1),
                        Occurrence("x__collision-1", "x", "Submodel", 1),
                    ),
                ),
                ("restore", (Rename("x", "x__collision-1", 1),)),
            ],
        )
        self.assertEqual(result.collisions, (Collision("x", (("a.json",), ("b.json",))),))

    def test_unconvertible_documents_are_reported_and_skipped(self) -> None:
        graph = RecordingGraph()

        result = import_corpus(
            [_document("a.json"), _document("bad.json")],
            FakeParser({"a.json": _submodels(("x", "A"))}),
            graph,
        )

        self.assertEqual(
            result.not_imported,
            (ReadFailure("bad.json", "Not imported: not an AAS environment"),),
        )
        self.assertEqual(
            [call for call, _ in graph.calls], ["upload", "link", "occurrences", "restore"]
        )

    def test_unstorable_documents_are_reported_and_the_rest_imported(self) -> None:
        graph = RecordingGraph()
        parser = FakeParser({"a.json": {"unstorable": True}, "b.json": _submodels(("x", "A"))})

        result = import_corpus([_document("a.json"), _document("b.json")], parser, graph)

        self.assertEqual(
            result.not_imported,
            (ReadFailure("a.json", "Not imported: content cannot be stored"),),
        )
        self.assertEqual(
            [call for call, _ in graph.calls], ["upload", "link", "occurrences", "restore"]
        )


class TestBatches(unittest.TestCase):
    def test_documents_are_uploaded_fifty_at_a_time(self) -> None:
        names = [f"{n:03}.json" for n in range(120)]
        graph = RecordingGraph()

        import_corpus(
            [_document(name) for name in names],
            FakeParser({name: _submodels((name, "A")) for name in names}),
            graph,
        )

        self.assertEqual(graph.batches, [50, 50, 20])

    def test_a_rejected_batch_is_retried_document_by_document(self) -> None:
        names = [f"{n:02}.json" for n in range(5)]
        environments = {name: _submodels((name, "A")) for name in names}
        environments["02.json"] = {"unstorable": True}
        graph = RecordingGraph()

        result = import_corpus([_document(name) for name in names], FakeParser(environments), graph)

        self.assertEqual(graph.batches, [1, 1, 1, 1])
        self.assertEqual([failure.source for failure in result.not_imported], ["02.json"])
        self.assertEqual(result.imported, 4)


class TestFailedDocumentsCountNowhere(unittest.TestCase):
    def test_counts_and_collisions_leave_out_documents_not_imported(self) -> None:
        unstorable = {"submodels": [{"id": "x", "idShort": "A"}], "unstorable": True}
        parser = FakeParser(
            {
                "a.json": unstorable,
                "b.json": _submodels(("x", "B")),
                "c.json": _submodels(("x", "A")),
            }
        )

        result = import_corpus(
            [_document(n) for n in ("a.json", "b.json", "c.json")], parser, RecordingGraph()
        )

        self.assertEqual(
            {(o.id, o.documents) for o in result.occurrences}, {("x", 1), ("x__collision-1", 1)}
        )
        self.assertEqual(result.collisions, (Collision("x", (("c.json",), ("b.json",))),))


class TestFirstContentNotImported(unittest.TestCase):
    def _result(self, *names: str):
        environments = {"a.json": {"submodels": [{"id": "x", "idShort": "Z"}], "unstorable": True}}
        environments |= {name: _submodels(("x", name)) for name in names}
        return import_corpus(
            [_document(n) for n in environments], FakeParser(environments), RecordingGraph()
        )

    def test_remaining_contents_do_not_claim_the_id(self) -> None:
        result = self._result("b.json", "c.json")
        self.assertEqual(
            result.collisions, (Collision("x", (("b.json",), ("c.json",)), first_missing=True),)
        )
        first = import_section(result).blocks[-2]
        assert isinstance(first, Finding)
        self.assertIn("lead nowhere", first.message)
        self.assertNotIn("lead to this content", first.message)

    def test_a_single_remaining_content_is_still_reported(self) -> None:
        result = self._result("b.json")
        self.assertEqual(result.collisions, (Collision("x", (("b.json",),), first_missing=True),))


class TestImportSection(unittest.TestCase):
    def test_lists_counts_failures_and_collisions(self) -> None:
        result = ImportResult(
            imported=3,
            collisions=(Collision("x", (("a.json",), ("b.json", "c.json"))),),
            not_imported=(ReadFailure("bad.json", "Not imported: broken"),),
            occurrences=(
                Occurrence("x", "x", "Submodel", 1),
                Occurrence("x__collision-1", "x", "Submodel", 2),
                Occurrence("cd", "cd", "ConceptDescription", 3),
            ),
        )

        summary, repeated, failure, first, second = import_section(result).blocks

        assert isinstance(summary, Table) and isinstance(first, Finding)
        assert isinstance(second, Finding)
        self.assertEqual(summary.rows, ((3, 1, 1),))
        assert isinstance(repeated, Table)
        self.assertEqual(repeated.rows, (("cd", "ConceptDescription", 3), ("x", "Submodel", 2)))
        self.assertEqual(
            failure,
            Finding(
                "not-imported", Severity.ERROR, "Not imported: broken", (Location("bad.json"),)
            ),
        )
        self.assertTrue(first.message.startswith("Content 1 of 2 under id x."))
        self.assertEqual(first.locations, (Location("a.json", "x"),))
        self.assertTrue(second.message.startswith("Content 2 of 2 under id x."))
        self.assertEqual(second.locations, (Location("b.json", "x"), Location("c.json", "x")))


if __name__ == "__main__":
    unittest.main()
