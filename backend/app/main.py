"""FastAPI app. Bound to 127.0.0.1 only -- this server is never reachable off-machine."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import paths
from app.api.routes import router

HOST = "127.0.0.1"
PORT = 8787


def create_app() -> FastAPI:
    app = FastAPI(title="VideoDownloader", docs_url=None, redoc_url=None)
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
