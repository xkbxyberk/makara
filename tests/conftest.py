from __future__ import annotations

import http.server
import json
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "infojson"
MEDIA_DIR = Path(__file__).parent / "fixtures" / "media"
MEDIA_REQUESTS: list[dict[str, Any]] = []  # what the throttled endpoint was asked for


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


@pytest.fixture(scope="session")
def multi_audio() -> dict[str, Any]:
    return load_fixture("youtube_multi_audio")


@pytest.fixture(scope="session")
def many_subs() -> dict[str, Any]:
    return load_fixture("youtube_many_subs")


@pytest.fixture(scope="session")
def playlist() -> dict[str, Any]:
    return load_fixture("youtube_playlist_flat")


@pytest.fixture(scope="session")
def other_site() -> dict[str, Any]:
    return load_fixture("other_site")


@pytest.fixture(scope="session")
def test_media() -> Path:
    """FFmpeg-generated clips (testsrc/sine). Built on demand, never downloaded."""
    if not (MEDIA_DIR / "info.json").exists():
        script = Path(__file__).parent.parent / "scripts" / "make_test_media.py"
        subprocess.run([sys.executable, str(script)], check=True)
    return MEDIA_DIR


@pytest.fixture(scope="session")
def media_server(test_media: Path) -> Iterator[str]:
    """Serve the test media over HTTP on loopback, so yt-dlp's real downloader is exercised."""

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def translate_path(self, path: str) -> str:
            return str(test_media / path.split("?")[0].removeprefix("/slow").lstrip("/"))

        def do_GET(self) -> None:
            if not self.path.startswith("/slow/"):
                super().do_GET()
                return
            # A throttled, Range-capable endpoint: lets a test cancel mid-download and then
            # prove that a retry *resumed* (sent a Range header) rather than starting over.
            path = Path(self.translate_path(self.path))
            data = path.read_bytes()
            start = 0
            range_header = self.headers.get("Range")
            if range_header and range_header.startswith("bytes="):
                start = int(range_header[6:].split("-")[0] or 0)
                MEDIA_REQUESTS.append({"path": self.path, "range_start": start})
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
            else:
                MEDIA_REQUESTS.append({"path": self.path, "range_start": None})
                self.send_response(200)
            self.send_header("Content-Length", str(len(data) - start))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            try:
                for offset in range(start, len(data), 8192):
                    self.wfile.write(data[offset : offset + 8192])
                    self.wfile.flush()
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def local_info(media_server: str, test_media: Path) -> dict[str, Any]:
    text = (test_media / "info.json").read_text()
    return json.loads(text.replace("{base}", media_server))
