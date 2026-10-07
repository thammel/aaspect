import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import jinja2
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse, Response

from aaspect.adapters.web.store import ReportStore
from aaspect.adapters.web.uploads import AUTO, UploadRejected, read_form
from aaspect.domain.corpus import Upload
from aaspect.domain.metamodel import NEWEST_FIRST, MetamodelVersion
from aaspect.domain.report import Report
from aaspect.ports.report_writer import ReportWriter

type Analyse = Callable[[Sequence[Upload], MetamodelVersion | None], Report]

# Pages show this much; the JSON download always has everything.
_MAX_ROWS = 200
_MAX_LOCATIONS = 20
_EXPIRED = "This report does not exist or has expired."


@dataclass(frozen=True, slots=True)
class WebLimits:
    max_upload_bytes: int
    max_files: int
    max_concurrent_analyses: int
    max_stored_reports: int


class Pages:
    def __init__(self, environment: jinja2.Environment, limits: WebLimits) -> None:
        self._environment = environment
        self._limits = {
            "max_upload_mb": limits.max_upload_bytes // 2**20,
            "max_upload_bytes": limits.max_upload_bytes,
            "max_files": limits.max_files,
        }

    def render(self, name: str, status: int = 200, **context: object) -> Response:
        html = self._environment.get_template(name).render(**self._limits, **context)
        return Response(html, status_code=status, media_type="text/html")

    def error(self, status: int, message: str) -> Response:
        return self.render("error.html", status, status_code=status, message=message)


def router(analyse: Analyse, writer: ReportWriter, pages: Pages, limits: WebLimits) -> APIRouter:
    handlers = _Handlers(analyse, writer, pages, limits)
    routes = APIRouter()
    routes.add_api_route("/", handlers.upload_form, methods=["GET"])
    routes.add_api_route("/analyses", handlers.start_analysis, methods=["POST"])
    routes.add_api_route("/reports/{key}", handlers.show_report, methods=["GET"])
    routes.add_api_route("/reports/{key}/report.json", handlers.download, methods=["GET"])
    return routes


class _Handlers:
    def __init__(
        self, analyse: Analyse, writer: ReportWriter, pages: Pages, limits: WebLimits
    ) -> None:
        self._analyse = analyse
        self._writer = writer
        self._pages = pages
        self._max_files = limits.max_files
        self._store = ReportStore(limits.max_stored_reports)
        # Each analysis holds its uploads in memory; queue instead of running them all.
        self._gate = threading.BoundedSemaphore(limits.max_concurrent_analyses)

    def upload_form(self) -> Response:
        versions = [AUTO, *(version.value for version in NEWEST_FIRST)]
        return self._pages.render("upload.html", versions=versions)

    async def start_analysis(self, request: Request) -> Response:
        try:
            uploads, version = await read_form(request, self._max_files)
        except UploadRejected as rejected:
            return self._pages.error(rejected.status, rejected.message)
        # Validation is CPU-bound; running it on the event loop would block every request.
        report = await run_in_threadpool(self._analyse_gated, uploads, version)
        return RedirectResponse(f"/reports/{self._store.add(report)}", status_code=303)

    def show_report(self, key: str) -> Response:
        report = self._store.get(key)
        if report is None:
            return self._pages.error(404, _EXPIRED)
        return self._pages.render(
            "report.html", report=report, key=key, max_rows=_MAX_ROWS, max_locations=_MAX_LOCATIONS
        )

    def download(self, key: str) -> Response:
        report = self._store.get(key)
        if report is None:
            return self._pages.error(404, _EXPIRED)
        return Response(
            self._writer.write(report),
            media_type=self._writer.media_type,
            headers={"content-disposition": 'attachment; filename="aaspect-report.json"'},
        )

    def _analyse_gated(self, uploads: list[Upload], version: MetamodelVersion | None) -> Report:
        with self._gate:
            return self._analyse(uploads, version)
