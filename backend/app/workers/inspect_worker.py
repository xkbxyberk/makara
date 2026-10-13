"""Run one `extract_info` in its own process.

Isolating the extractor means a yt-dlp crash, a hang or a cancel can never take the server down:
the parent just kills the child's process group. The contract is one JSON request on stdin and
one JSON response on stdout. yt-dlp's own output goes through `Collector`, never to stdout.
"""

from __future__ import annotations

import json
import os
import sys
from collections import deque
from typing import Any

from app import errors
from app.workers import lifeline, session
from app.ytdlp import params


class Collector:
    """A yt-dlp logger that keeps what the UI needs: warnings to act on, and a raw tail."""

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.tail: deque[str] = deque(maxlen=40)

    def debug(self, msg: str) -> None:
        self.tail.append(msg)

    def info(self, msg: str) -> None:
        self.tail.append(msg)

    def warning(self, msg: str) -> None:
        self.warnings.append(msg)
        self.tail.append(f"WARNING: {msg}")

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        self.tail.append(msg)

    def raw(self, exc: BaseException | None = None) -> str:
        lines = list(self.tail)
        if exc is not None and str(exc) not in lines:
            lines.append(str(exc))
        return "\n".join(lines)[-4000:]


def run(request: dict[str, Any]) -> dict[str, Any]:
    import yt_dlp

    log = Collector()
    options = {**params.inspect_params(), "logger": log, "no_warnings": False}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            # YouTube's part of the Safari session, only when the server asks for it.
            session.apply(ydl, request.get("cookies_from_browser"))
            info = ydl.extract_info(request["url"], download=False)
            if info is None:
                message = log.errors[-1] if log.errors else "extract_info returned None"
                raise errors.AppError(code=errors.classify(message), raw=log.raw())
            return {
                "ok": True,
                "info": ydl.sanitize_info(info),
                "warnings": errors.classify_warnings(log.warnings),
            }
    except errors.AppError as exc:
        return {"ok": False, "error": exc.as_dict()}
    except Exception as exc:  # any extractor failure becomes a coded error
        return {"ok": False, "error": {**errors.from_exception(exc).as_dict(), "raw": log.raw(exc)}}


def main() -> int:
    lifeline.hold()
    request = json.loads(sys.stdin.read())
    # Anything yt-dlp or a library prints must not corrupt the one JSON line we answer with.
    out = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)  # child processes inherit fd 1; keep them off the answer channel too
    sys.stdout = sys.stderr
    out.write(json.dumps(run(request)))
    out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
