"""FastAPI app. Bound to 127.0.0.1 only -- this server is never reachable off-machine."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import signal
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import db, errors, paths
from app import settings as settings_store
from app.api import jobs_api, library_api, studio_api
from app.api.routes import router
from app.jobs.manager import JobManager
from app.library import Library
from app.system import ClipboardWatcher

_MEDIA_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
log = logging.getLogger("videodownloader")

HOST = paths.SERVER_HOST
PORT = paths.SERVER_PORT
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
ALLOWED_ORIGINS = {f"http://{host}:{port}" for host in ALLOWED_HOSTS for port in (PORT, 5173)}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def reject_cross_site(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """A web page on another origin must not be able to drive this API (e.g. cancel jobs with
    a bodiless form POST). Same-origin fetches from our own UI pass; so do non-browser tools."""
    if request.method not in SAFE_METHODS:
        origin = request.headers.get("origin")
        site = request.headers.get("sec-fetch-site")
        if (origin and origin not in ALLOWED_ORIGINS) or site == "cross-site":
            return JSONResponse(status_code=403, content={"error": {"code": "FORBIDDEN_ORIGIN"}})
    return await call_next(request)


def _log_task_failure(task: asyncio.Task[Any]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None and not (isinstance(exc, errors.AppError) and exc.code == "SCAN_BUSY"):
        log.error("background task failed", exc_info=exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Two connections: the job store lives on the event loop; the library is also used from
    # worker threads and guards its own connection with a lock.
    library = Library(db.connect())

    def catalogue(job: dict[str, Any], outcome: dict[str, Any]) -> None:
        item = library.add(job=job, outcome=outcome)
        if item is not None:
            manager.publish({"type": "library", "item": item})

    manager = JobManager(db.JobStore(db.connect()), settings_store.load, on_done=catalogue)
    clipboard = ClipboardWatcher(lambda: settings_store.load().clipboard_watch, manager.publish)
    app.state.jobs = manager
    app.state.library = library
    await manager.start()
    clipboard.start()
    # Files may have been moved or deleted in Finder while the app was closed.
    scan = asyncio.create_task(
        asyncio.to_thread(library.scan, [Path(settings_store.load().download_dir).expanduser()])
    )
    scan.add_done_callback(_log_task_failure)
    orphan_watch = _watch_parent()
    try:
        yield
    finally:
        if orphan_watch is not None:
            orphan_watch.cancel()
        clipboard.stop()
        await manager.stop()
        with contextlib.suppress(asyncio.CancelledError, errors.AppError):
            await asyncio.wait_for(asyncio.shield(scan), timeout=5)


PARENT_CHECK_SECONDS = 1.0


def _watch_parent() -> asyncio.Task[None] | None:
    """Started by VideoDownloader.app (`VD_PARENT_PID`), the server must not outlive it: if the
    app crashes or is killed, this process is re-parented, notices, and shuts down cleanly --
    which stops every worker -- instead of holding the port and the queue forever."""
    raw = os.environ.get("VD_PARENT_PID")
    if not raw or not raw.isdigit():
        return None
    parent = int(raw)

    async def watch() -> None:
        while os.getppid() == parent:
            await asyncio.sleep(PARENT_CHECK_SECONDS)
        log.warning("parent process %s is gone; shutting down", parent)
        os.kill(os.getpid(), signal.SIGTERM)  # uvicorn's own graceful shutdown path

    task = asyncio.create_task(watch())
    task.add_done_callback(_log_task_failure)
    return task


def create_app() -> FastAPI:
    app = FastAPI(title="VideoDownloader", docs_url=None, redoc_url=None, lifespan=lifespan)
    # A DNS-rebinding page resolves its own hostname to 127.0.0.1; the Host header gives it away.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.middleware("http")(reject_cross_site)
    app.include_router(router)
    app.include_router(jobs_api.router)
    app.include_router(library_api.router)
    app.include_router(studio_api.router)

    if paths.fixture_mode():
        # Test-only: serve the generated clips so downloads run offline against this server.
        @app.get("/fixture-media/{name}", response_model=None)
        def fixture_media(name: str) -> FileResponse | JSONResponse:
            path = paths.MEDIA_FIXTURE_DIR / name
            if not _MEDIA_NAME.match(name) or not path.is_file():
                return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND"}})
            return FileResponse(path)

        # Test-only, fixture mode only: drive the clipboard banner without the real clipboard.
        @app.post("/api/test/clipboard")
        async def fake_clipboard(request: Request) -> dict[str, bool]:
            body = await request.json()
            request.app.state.jobs.publish({"type": "clipboard", "url": str(body["url"])})
            return {"ok": True}

    dist = paths.FRONTEND_DIST
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", response_model=None)
        def spa(full_path: str) -> FileResponse | JSONResponse:
            index = dist / "index.html"
            if not index.exists():
                return JSONResponse(status_code=404, content={"error": {"code": "NO_FRONTEND"}})
            return FileResponse(index)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    class _AnnouncingServer(uvicorn.Server):
        """Tell open event streams to end the moment a stop is asked for. They otherwise end
        only in the lifespan shutdown, which uvicorn reaches after waiting for open connections
        -- so every quit waited out the timeout above and logged a cancelled task."""

        def handle_exit(self, sig: int, frame: Any) -> None:
            super().handle_exit(sig, frame)
            manager = getattr(app.state, "jobs", None)
            if manager is not None:
                manager.announce_shutdown()

    print(f"VideoDownloader listening on http://{HOST}:{PORT}/", file=sys.stderr, flush=True)
    # An open event stream (a browser tab, the app's web view) only ends when the manager
    # shuts down -- which happens after uvicorn stops waiting for open connections. Without a
    # limit, SIGTERM never got that far: the app waited, then had to SIGKILL, and running
    # workers (in their own sessions) were left behind.
    config = uvicorn.Config(
        app, host=HOST, port=PORT, log_level="warning", timeout_graceful_shutdown=2
    )
    _AnnouncingServer(config).run()


if __name__ == "__main__":
    main()
