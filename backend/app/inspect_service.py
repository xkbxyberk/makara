"""Drive the inspect worker, or serve a recorded fixture when the app runs offline."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from typing import Any

from app import errors, paths
from app.ytdlp import command, normalize

INSPECT_TIMEOUT_SECONDS = 180

# Fixture mode keys off whatever is recognisable in the URL, so the e2e suite can use
# realistic-looking links without ever reaching the network.
_FIXTURE_MATCHERS: list[tuple[str, str]] = [
    (r"0e3GPea1Tyg|multi[-_]?audio", "youtube_multi_audio"),
    (r"iG9CE55wbtY|many[-_]?subs", "youtube_many_subs"),
    (r"playlist|@TED|/videos", "youtube_playlist_flat"),
    (r"archive\.org|other[-_]?site", "other_site"),
]

_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def validate_url(url: str) -> str:
    url = url.strip()
    if not _URL_RE.match(url):
        raise errors.AppError(code="INVALID_URL", raw=url)
    return url


def _fixture_for(url: str) -> dict[str, Any]:
    for pattern, name in _FIXTURE_MATCHERS:
        if re.search(pattern, url, re.IGNORECASE):
            path = paths.FIXTURE_DIR / f"{name}.json"
            if path.exists():
                return json.loads(path.read_text())
    raise errors.AppError(code="UNSUPPORTED_SITE", raw=f"no fixture matches {url}")


async def _run_worker(url: str, *, flat: bool) -> dict[str, Any]:
    env = dict(os.environ)
    backend_dir = str(paths.PROJECT_ROOT / "backend")
    env["PYTHONPATH"] = (
        backend_dir + os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else backend_dir
    )
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.workers.inspect_worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(paths.PROJECT_ROOT),
    )
    payload = json.dumps({"url": url, "flat": flat}).encode()
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(payload), timeout=INSPECT_TIMEOUT_SECONDS
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise errors.AppError(
            code="TIMEOUT", raw=f"inspect exceeded {INSPECT_TIMEOUT_SECONDS}s"
        ) from None
    if not stdout:
        raise errors.AppError(code=errors.UNKNOWN, raw=stderr.decode()[-2000:])
    result: dict[str, Any] = json.loads(stdout)
    if not result.get("ok"):
        err = result["error"]
        raise errors.AppError(code=err["code"], raw=err["raw"], detail=err.get("detail", {}))
    info: dict[str, Any] = result["info"]
    return info


async def inspect(url: str, *, flat: bool = False) -> dict[str, Any]:
    url = validate_url(url)
    info = _fixture_for(url) if paths.fixture_mode() else await _run_worker(url, flat=flat)
    model = normalize.normalize(info)
    model["source_url"] = url
    model["commands"] = {
        "inspect": command.quote(command.inspect_command(url)),
        "suggested": command.quote(command.command_for_model(model, url)),
    }
    return model
