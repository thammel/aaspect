"""Submodel templates uploaded with an analysis, checked against before IDTA's own."""

from collections.abc import Sequence

from aaspect.domain.corpus import Upload
from aaspect.domain.report import ShownError
from aaspect.domain.templates.catalogue import Catalogue, CatalogueProblem, TemplateFile, Tier
from aaspect.ports.corpus_reader import CorpusReader
from aaspect.ports.environment_parser import EnvironmentParser
from aaspect.ports.template_source import TemplateSource


def read_templates(
    uploads: Sequence[Upload], reader: CorpusReader, parser: EnvironmentParser
) -> tuple[list[TemplateFile], list[CatalogueProblem]]:
    """Each AAS document in the uploads as a template file, and why the others are left
    out. Read like the corpus, within the same limits, since they are as untrusted."""
    corpus = reader.read(uploads)
    files: list[TemplateFile] = []
    problems = [CatalogueProblem(failure.source, failure.reason) for failure in corpus.failures]
    for document in corpus.documents:
        try:
            environment = parser.parse(document)
        except ValueError as error:
            problems.append(CatalogueProblem(document.label, str(error)))
            continue
        files.append(TemplateFile(document.label, Tier.CUSTOM, environment))
    return files, problems


class WithUploaded:
    """A `TemplateSource`: `base` extended by the uploaded templates. While the base has
    none to give, the uploaded ones are used alone, and the report says why."""

    def __init__(
        self,
        base: TemplateSource | None,
        files: Sequence[TemplateFile],
        problems: Sequence[CatalogueProblem],
    ) -> None:
        self._base = base
        self._files = files
        self._problems = problems

    def catalogue(self) -> Catalogue:
        base = None
        problems = list(self._problems)
        if self._base is not None:
            try:
                base = self._base.catalogue()
            except ShownError as error:
                if not self._files:
                    raise
                problems.append(CatalogueProblem("IDTA templates", str(error)))
        return Catalogue(self._files, base=base, problems=problems)


def with_uploaded(
    base: TemplateSource | None,
    uploads: Sequence[Upload],
    reader: CorpusReader,
    parser: EnvironmentParser | None,
) -> TemplateSource | None:
    """The template source of one analysis: `base`, extended by its uploaded templates."""
    if not uploads or parser is None:
        return base
    files, problems = read_templates(uploads, reader, parser)
    return WithUploaded(base, files, problems)
