from collections.abc import Callable, Sequence

from aaspect.app import schema_check
from aaspect.domain.corpus import Upload
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Report, Section, SectionStatus
from aaspect.ports.corpus_reader import CorpusReader
from aaspect.ports.schema_validator import SchemaValidator


class AnalyseCorpus:
    def __init__(
        self,
        reader: CorpusReader,
        validator: SchemaValidator,
        aaspect_version: str,
        map_documents: schema_check.MapDocuments = map,
    ) -> None:
        self._reader = reader
        self._validator = validator
        self._aaspect_version = aaspect_version
        self._map_documents = map_documents

    def run(self, uploads: Sequence[Upload], requested_version: MetamodelVersion | None) -> Report:
        corpus = self._reader.read(uploads)
        schema = _guarded(
            schema_check.SECTION_KEY,
            schema_check.SECTION_TITLE,
            lambda: schema_check.check_schema(
                corpus, self._validator, requested_version, self._map_documents
            ),
        )
        return Report(
            aaspect_version=self._aaspect_version,
            files=tuple(upload.name for upload in uploads),
            sections=(schema,),
        )


def _guarded(key: str, title: str, analysis: Callable[[], Section]) -> Section:
    try:
        return analysis()
    except Exception as error:  # One failing analysis must not take the whole report down.
        return Section(key, title, SectionStatus.FAILED, reason=f"{type(error).__name__}: {error}")
