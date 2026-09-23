"""FastAPI app. Bound to 127.0.0.1 only -- this server is never reachable off-machine."""

from __future__ import annotations

import asyncio
import re
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import db, paths
from app import settings as settings_store
from app.api import jobs_api, library_api
from app.api.routes import router
from app.jobs.manager import JobManager
from app.library import Library
from app.system import ClipboardWatcher

_MEDIA_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")

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
    try:
        yield
    finally:
        scan.cancel()
        clipboard.stop()
        await manager.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="VideoDownloader", docs_url=None, redoc_url=None, lifespan=lifespan)
    # A DNS-rebinding page resolves its own hostname to 127.0.0.1; the Host header gives it away.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.middleware("http")(reject_cross_site)
    app.include_router(router)
    app.include_router(jobs_api.router)
    app.include_router(library_api.router)

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

    print(f"VideoDownloader listening on http://{HOST}:{PORT}/", file=sys.stderr, flush=True)
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
