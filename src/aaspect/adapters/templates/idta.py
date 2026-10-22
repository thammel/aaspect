"""The IDTA submodel templates, downloaded at runtime from one pinned commit of IDTA's
repository and kept in memory, compiled.

The templates are IDTA's, under CC BY 4.0 with possibly further terms per template, so
AASpect does not redistribute them: `manifest.json` lists only their paths, sizes and
hashes, written by `tools/template_manifest.py`.
"""

import hashlib
import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from importlib import resources
from typing import Any

from aaspect.domain.report import ShownError
from aaspect.domain.templates.catalogue import Catalogue, TemplateFile, Tier

logger = logging.getLogger(__name__)

RAW_URL = "https://raw.githubusercontent.com"
_TIERS = {"current": Tier.CURRENT, "superseded": Tier.SUPERSEDED, "withdrawn": Tier.WITHDRAWN}
_UNAVAILABLE = (
    "The IDTA submodel templates are not available: their download has not succeeded yet."
    " The server log has the details."
)
# All files together; one stalled connection must not hold the download forever.
_TOTAL_SECONDS = 300
_READ_BYTES = 2**16

type Fetch = Callable[[str, int, float], bytes]


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


# HTTPS only, and no redirects: a mirror must serve the files at their paths. Built by
# hand, since the default opener also reads file: and ftp: addresses.
_OPENER = urllib.request.OpenerDirector()
for _handler in (
    urllib.request.HTTPSHandler(),
    _NoRedirects(),
    urllib.request.HTTPDefaultErrorHandler(),
    urllib.request.HTTPErrorProcessor(),
):
    _OPENER.add_handler(_handler)


def _fetch(url: str, size: int, deadline: float) -> bytes:
    """Exactly `size` bytes from `url`, before `deadline` (a `time.monotonic` value)."""
    with _OPENER.open(url, timeout=30) as reply:
        content = bytearray()
        while len(content) <= size:
            if time.monotonic() > deadline:
                raise TimeoutError("the download took too long")
            piece = reply.read(min(_READ_BYTES, size + 1 - len(content)))
            if not piece:
                break
            content += piece
    if len(content) != size:
        raise ValueError("file of another size than pinned")
    return bytes(content)


class IdtaTemplates:
    """`start` downloads in the background and retries every `retry_seconds` until it
    succeeds; analyses never wait for the network."""

    def __init__(
        self,
        base_url: str = RAW_URL,
        fetch: Fetch = _fetch,
        manifest: dict[str, Any] | None = None,
        retry_seconds: float = 300,
        workers: int = 8,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("the templates URL must start with https://")
        self._manifest = manifest or json.loads(
            resources.files(__package__).joinpath("manifest.json").read_text("utf-8")
        )
        self._base_url = base_url.rstrip("/")
        self._fetch = fetch
        self._retry_seconds = retry_seconds
        self._workers = workers
        self._lock = threading.Lock()
        self._catalogue: Catalogue | None = None

    def start(self) -> None:
        threading.Thread(target=self._keep_trying, daemon=True).start()

    def catalogue(self) -> Catalogue:
        with self._lock:
            if self._catalogue is None:
                raise ShownError(_UNAVAILABLE)
            return self._catalogue

    def load(self) -> bool:
        """Download every file of the manifest once; False, logged, if one fails."""
        deadline = time.monotonic() + _TOTAL_SECONDS
        pool = ThreadPoolExecutor(self._workers)
        try:
            files = list(pool.map(lambda entry: self._file(entry, deadline), self._entries()))
            catalogue = Catalogue(files)
        except Exception:  # Any failure leaves the templates unavailable until a retry.
            logger.warning("Downloading the IDTA submodel templates failed", exc_info=True)
            return False
        finally:
            # The first failure decides; the files not yet fetched are not waited for.
            pool.shutdown(wait=False, cancel_futures=True)
        with self._lock:
            self._catalogue = catalogue
        logger.info("Downloaded %d IDTA submodel templates", len(files))
        return True

    def _keep_trying(self) -> None:
        while not self.load():
            time.sleep(self._retry_seconds)

    def _entries(self) -> list[dict[str, Any]]:
        return self._manifest["files"]

    def _file(self, entry: dict[str, Any], deadline: float) -> TemplateFile:
        path = urllib.parse.quote(entry["path"])
        url = f"{self._base_url}/{self._manifest['repository']}/{self._manifest['commit']}/{path}"
        content = self._fetch(url, entry["size"], deadline)
        if hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError(f"{entry['path']}: content differs from the pinned version")
        environment = json.loads(content.decode("utf-8-sig"))
        if not isinstance(environment, dict):
            raise ValueError(f"{entry['path']}: not an AAS environment")
        version = tuple(entry["version"])
        stem = entry["path"].rsplit("/", 1)[1].removesuffix(".json")
        # Editions of one template can have the same file name.
        name = f"{stem} ({'.'.join(map(str, version))})" if version else stem
        return TemplateFile(name, _TIERS[entry["tier"]], environment, version, entry["priority"])
