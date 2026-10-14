import time
from collections.abc import Callable, Sequence

from aaspect.app import import_corpus, schema_check
from aaspect.app.schema_check import SchemaCheckResult
from aaspect.domain.corpus import Corpus, Upload
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Report, Section, SectionStatus
from aaspect.ports.corpus_reader import CorpusReader
from aaspect.ports.environment_parser import EnvironmentParser
from aaspect.ports.graph_store import GraphStore
from aaspect.ports.schema_validator import SchemaValidator

type Progress = Callable[[Report], None]


class AnalyzeCorpus:
    def __init__(
        self,
        reader: CorpusReader,
        validator: SchemaValidator,
        aaspect_version: str,
        map_documents: schema_check.MapDocuments = map,
        time_limit_seconds: float = float("inf"),
        graph_store: GraphStore | None = None,
        parser: EnvironmentParser | None = None,
    ) -> None:
        self._reader = reader
        self._validator = validator
        self._aaspect_version = aaspect_version
        self._map_documents = map_documents
        self._time_limit = time_limit_seconds
        self._graph_store = graph_store
        self._parser = parser

    def run(
        self,
        uploads: Sequence[Upload],
        requested_version: MetamodelVersion | None,
        progress: Progress = lambda report: None,
    ) -> Report:
        """The finished report; `progress` also receives every state on the way there."""
        sections = {
            schema_check.SECTION_KEY: Section(
                schema_check.SECTION_KEY, schema_check.SECTION_TITLE, SectionStatus.WAITING
            ),
            import_corpus.SECTION_KEY: self._graph_waiting(),
        }

        def publish() -> Report:
            report = Report(
                aaspect_version=self._aaspect_version,
                files=tuple(upload.name for upload in uploads),
                sections=tuple(sections.values()),
            )
            progress(report)
            return report

        publish()
        sections[schema_check.SECTION_KEY] = Section(
            schema_check.SECTION_KEY, schema_check.SECTION_TITLE, SectionStatus.RUNNING
        )
        publish()
        corpus = self._reader.read(uploads)
        sections[schema_check.SECTION_KEY] = self._check_schema(corpus, requested_version).section
        if sections[import_corpus.SECTION_KEY].status is SectionStatus.WAITING:
            sections[import_corpus.SECTION_KEY] = Section(
                import_corpus.SECTION_KEY, import_corpus.SECTION_TITLE, SectionStatus.RUNNING
            )
            publish()
            sections[import_corpus.SECTION_KEY] = self._import_graph(corpus)
        return publish()

    def _check_schema(
        self, corpus: Corpus, requested_version: MetamodelVersion | None
    ) -> SchemaCheckResult:
        # One upload of crafted files could otherwise keep every worker busy for hours.
        deadline = time.monotonic() + self._time_limit
        try:
            return schema_check.check_schema(
                corpus,
                self._validator,
                requested_version,
                self._map_documents,
                lambda: time.monotonic() > deadline,
            )
        except Exception as error:  # One failing analysis must not take the whole report down.
            return SchemaCheckResult(
                _failed(schema_check.SECTION_KEY, schema_check.SECTION_TITLE, error)
            )

    def _graph_waiting(self) -> Section:
        if self._graph_store is None or self._parser is None:
            return Section(
                import_corpus.SECTION_KEY,
                import_corpus.SECTION_TITLE,
                SectionStatus.SKIPPED,
                reason="No graph database is configured.",
            )
        return Section(
            import_corpus.SECTION_KEY, import_corpus.SECTION_TITLE, SectionStatus.WAITING
        )

    def _import_graph(self, corpus: Corpus) -> Section:
        assert self._graph_store is not None and self._parser is not None
        try:
            with self._graph_store.open() as graph:
                result = import_corpus.import_corpus(corpus.documents, self._parser, graph)
            return import_corpus.import_section(result)
        except Exception as error:  # One failing analysis must not take the whole report down.
            return _failed(import_corpus.SECTION_KEY, import_corpus.SECTION_TITLE, error)


def _failed(key: str, title: str, error: Exception) -> Section:
    return Section(key, title, SectionStatus.FAILED, reason=f"{type(error).__name__}: {error}")
