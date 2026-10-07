"""Composition root: the only place that constructs adapters and wires them together."""

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from functools import partial
from importlib.metadata import version

import uvicorn
from fastapi import FastAPI

from aaspect.adapters.files.aasx import ArchiveLimits
from aaspect.adapters.files.reader import FileCorpusReader
from aaspect.adapters.report_json.writer import JsonReportWriter
from aaspect.adapters.schema.isolated import IsolatedSchemaValidator
from aaspect.adapters.schema.validator import OfficialSchemaValidator
from aaspect.adapters.web.app import create_app
from aaspect.adapters.web.routes import WebLimits
from aaspect.app.analyse_corpus import AnalyseCorpus
from aaspect.config.settings import Settings, load_settings


def build_app(settings: Settings, resources: ExitStack) -> FastAPI:
    """The web app; worker processes and threads are released when `resources` closes."""
    validator = IsolatedSchemaValidator(
        partial(OfficialSchemaValidator, settings.max_violations_per_document),
        workers=settings.validation_workers,
        timeout_seconds=settings.validation_timeout_seconds,
        memory_bytes=settings.worker_memory_bytes,
    )
    resources.callback(validator.close)
    # One thread per worker process: the threads only wait for their worker.
    pool = resources.enter_context(ThreadPoolExecutor(settings.validation_workers))
    reader = FileCorpusReader(
        ArchiveLimits(
            max_part_bytes=settings.max_part_bytes,
            max_entries=settings.max_archive_entries,
            max_compression_ratio=settings.max_compression_ratio,
            max_parts=settings.max_aas_parts,
        ),
        max_document_bytes=settings.max_document_bytes,
    )
    analyse = AnalyseCorpus(reader, validator, version("aaspect"), pool.map)
    limits = WebLimits(
        max_upload_bytes=settings.max_upload_bytes,
        max_files=settings.max_files,
        max_concurrent_analyses=settings.max_concurrent_analyses,
        max_stored_reports=settings.max_stored_reports,
    )
    allowed_hosts = [host.strip() for host in settings.allowed_hosts.split(",") if host.strip()]
    return create_app(analyse.run, JsonReportWriter(), limits, allowed_hosts)


def main() -> None:
    settings = load_settings(os.environ)
    with ExitStack() as resources:
        uvicorn.run(build_app(settings, resources), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
