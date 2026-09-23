"""FastAPI app. Bound to 127.0.0.1 only -- this server is never reachable off-machine."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import paths
from app.api.routes import router

HOST = "127.0.0.1"
PORT = 8787
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


def create_app() -> FastAPI:
    app = FastAPI(title="VideoDownloader", docs_url=None, redoc_url=None)
    # A DNS-rebinding page resolves its own hostname to 127.0.0.1; the Host header gives it away.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.middleware("http")(reject_cross_site)
    app.include_router(router)

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

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
