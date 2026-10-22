"""The IDTA submodel templates, downloaded at runtime from one pinned commit of IDTA's
repository and kept in memory.

The templates are IDTA's, under CC BY 4.0 with possibly further terms per template, so
AASpect does not redistribute them: `manifest.json` lists only their paths and hashes,
written by `tools/template_manifest.py`.
"""

import hashlib
import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from importlib import resources
from typing import Any

from aaspect.domain.report import ShownError
from aaspect.domain.templates.catalogue import TemplateFile, Tier

logger = logging.getLogger(__name__)

RAW_URL = "https://raw.githubusercontent.com"
_TIERS = {"current": Tier.CURRENT, "superseded": Tier.SUPERSEDED, "withdrawn": Tier.WITHDRAWN}
# The largest IDTA template is about 3 MB.
_MAX_BYTES = 32 * 2**20
_UNAVAILABLE = (
    "The IDTA submodel templates could not be downloaded; the server log has the details."
)

type Fetch = Callable[[str], bytes]


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as reply:  # noqa: S310 - fixed https base
        content = reply.read(_MAX_BYTES + 1)
    if len(content) > _MAX_BYTES:
        raise ValueError("file larger than expected")
    return content


class IdtaTemplates:
    """Downloads every template of the manifest once; a failed download is tried again
    on a later request, at most every `retry_seconds`."""

    def __init__(
        self,
        base_url: str = RAW_URL,
        fetch: Fetch = _fetch,
        manifest: dict[str, Any] | None = None,
        retry_seconds: float = 300,
        workers: int = 8,
    ) -> None:
        self._manifest = manifest or json.loads(
            resources.files(__package__).joinpath("manifest.json").read_text("utf-8")
        )
        self._base_url = base_url.rstrip("/")
        self._fetch = fetch
        self._retry_seconds = retry_seconds
        self._workers = workers
        self._lock = threading.Lock()
        self._files: tuple[TemplateFile, ...] | None = None
        self._failed_at: float | None = None

    def prefetch(self) -> None:
        """Start the download in the background, so the first analysis need not wait."""
        threading.Thread(target=self._try_load, daemon=True).start()

    def templates(self) -> Sequence[TemplateFile]:
        with self._lock:
            if self._files is None:
                recent = self._failed_at is not None and (
                    time.monotonic() - self._failed_at < self._retry_seconds
                )
                if recent or not self._load():
                    raise ShownError(_UNAVAILABLE)
            assert self._files is not None
            return self._files

    def _try_load(self) -> None:
        with self._lock:
            if self._files is None:
                self._load()

    def _load(self) -> bool:
        entries = self._manifest["files"]
        try:
            with ThreadPoolExecutor(self._workers) as pool:
                self._files = tuple(pool.map(self._file, entries))
        except Exception:  # Any failure leaves the templates unavailable until a retry.
            logger.warning("Downloading the IDTA submodel templates failed", exc_info=True)
            self._failed_at = time.monotonic()
            return False
        logger.info("Downloaded %d IDTA submodel templates", len(self._files))
        return True

    def _file(self, entry: dict[str, Any]) -> TemplateFile:
        path = urllib.parse.quote(entry["path"])
        url = f"{self._base_url}/{self._manifest['repository']}/{self._manifest['commit']}/{path}"
        content = self._fetch(url)
        if _git_blob_sha(content) != entry["sha"]:
            raise ValueError(f"{entry['path']}: content differs from the pinned version")
        environment = json.loads(content.decode("utf-8-sig"))
        if not isinstance(environment, dict):
            raise ValueError(f"{entry['path']}: not an AAS environment")
        name = entry["path"].rsplit("/", 1)[1].removesuffix(".json")
        return TemplateFile(name, _TIERS[entry["tier"]], environment, tuple(entry["version"]))


def _git_blob_sha(content: bytes) -> str:
    """The hash git names a file by, which the manifest records for each template."""
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()
