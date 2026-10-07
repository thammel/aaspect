from collections.abc import Sequence

from aaspect.adapters.files.aasx import ArchiveLimits, aas_parts
from aaspect.adapters.files.sniff import Kind, Unreadable, document, sniff
from aaspect.domain.corpus import AasDocument, Corpus, ReadFailure, Upload


class FileCorpusReader:
    """Reads uploaded JSON, XML and AASX files. Any problem with one file becomes a
    `ReadFailure` for that file; the others are still read."""

    def __init__(self, limits: ArchiveLimits) -> None:
        self._limits = limits

    def read(self, uploads: Sequence[Upload]) -> Corpus:
        documents: list[AasDocument] = []
        failures: list[ReadFailure] = []
        for upload in uploads:
            try:
                documents.extend(self._documents(upload))
            except Unreadable as error:
                failures.append(ReadFailure(upload.name, str(error)))
        return Corpus(tuple(documents), tuple(failures))

    def _documents(self, upload: Upload) -> list[AasDocument]:
        if sniff(upload.content) is not Kind.ZIP:
            return [document(upload.name, upload.content)]
        return [
            document(upload.name, content, part)
            for part, content in aas_parts(upload.content, self._limits)
        ]
