"""Run one `extract_info` in its own process.

Isolating the extractor means a yt-dlp crash, a hang or a cancel can never take the
server down: the parent just kills the child. The contract is one JSON request on
stdin, one JSON response on stdout.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from app import errors
from app.ytdlp import params


def run(request: dict[str, Any]) -> dict[str, Any]:
    import yt_dlp

    url = request["url"]
    flat = bool(request.get("flat"))
    try:
        with yt_dlp.YoutubeDL(params.inspect_params(flat=flat)) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise errors.AppError(code="VIDEO_UNAVAILABLE", raw="extract_info returned None")
            return {"ok": True, "info": ydl.sanitize_info(info)}
    except errors.AppError as exc:
        return {"ok": False, "error": exc.as_dict()}
    except Exception as exc:  # any extractor failure becomes a coded error
        return {"ok": False, "error": errors.from_exception(exc).as_dict()}


def main() -> int:
    request = json.loads(sys.stdin.read())
    sys.stdout.write(json.dumps(run(request)))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
