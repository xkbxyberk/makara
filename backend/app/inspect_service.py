"""Drive the inspect worker, or serve a recorded fixture when the app runs offline."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import signal
import sys
from typing import Any

from app import errors, paths
from app.ytdlp import command, normalize
from app.ytdlp.params import find_js_runtimes

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


async def _run_worker(url: str) -> tuple[dict[str, Any], list[str]]:
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
        # Its own process group, so killing it also kills anything it spawned (deno, ffprobe).
        start_new_session=True,
    )
    payload = json.dumps({"url": url}).encode()
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(payload), timeout=INSPECT_TIMEOUT_SECONDS
        )
    except TimeoutError:
        raise errors.AppError(
            code="TIMEOUT", raw=f"inspect exceeded {INSPECT_TIMEOUT_SECONDS}s"
        ) from None
    finally:
        # Runs on timeout, on server shutdown (CancelledError) and on success alike.
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            await proc.wait()
    try:
        result: dict[str, Any] = json.loads(stdout)
    except ValueError:
        raise errors.AppError(
            code=errors.UNKNOWN, raw=(stderr or stdout).decode(errors="replace")[-4000:]
        ) from None
    if not result.get("ok"):
        err = result["error"]
        raise errors.AppError(code=err["code"], raw=err["raw"], detail=err.get("detail", {}))
    return result["info"], list(result.get("warnings") or [])


async def inspect(url: str) -> dict[str, Any]:
    url = validate_url(url)
    warnings: list[str] = []
    if paths.fixture_mode():
        info = _fixture_for(url)
    else:
        info, warnings = await _run_worker(url)
    model = normalize.normalize(info)
    extractor = str(model["media"].get("extractor") or "").lower()
    if extractor.startswith("youtube") and not find_js_runtimes():
        warnings.append("NO_JS_RUNTIME")
    model["warnings"] = [*model["warnings"], *(w for w in warnings if w not in model["warnings"])]
    model["source_url"] = url
    model["commands"] = {
        "inspect": command.quote(command.inspect_command(url)),
        "suggested": command.quote(command.command_for_model(model, url)),
    }
    return model
