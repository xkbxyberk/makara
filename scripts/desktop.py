"""Launch the server and show it in a native window, falling back to the browser."""

from __future__ import annotations

import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import HOST, PORT, app  # path is set up immediately above

URL = f"http://{HOST}:{PORT}/"


def _serve() -> None:
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def _wait_until_ready(timeout: float = 25.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{URL}api/health", timeout=1):  # localhost only
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.15)
    return False


def main() -> int:
    server = threading.Thread(target=_serve, daemon=True)
    server.start()
    if not _wait_until_ready():
        print("Server did not come up", file=sys.stderr)
        return 1
    try:
        import webview
    except ImportError:
        webbrowser.open(URL)
        server.join()
        return 0
    webview.create_window("VideoDownloader", URL, width=1240, height=860, min_size=(420, 600))
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
