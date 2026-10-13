"""Drive the inspect worker, or serve a recorded fixture when the app runs offline."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import signal
import sys
import time
import uuid
from collections import OrderedDict
from typing import Any

from app import browser_session, errors, paths
from app import settings as settings_store
from app.ytdlp import command, naming, normalize, offers, selection
from app.ytdlp.params import find_js_runtimes

INSPECT_TIMEOUT_SECONDS = 180

# Fixture mode keys off whatever is recognisable in the URL, so the e2e suite can use
# realistic-looking links without ever reaching the network.
_FIXTURE_MATCHERS: list[tuple[str, str]] = [
    (r"example\.test|local[-_]?media", "local_media"),
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
        if not re.search(pattern, url, re.IGNORECASE):
            continue
        if name == "local_media":
            # Generated clips whose format URLs point back at this server: downloadable offline.
            path = paths.MEDIA_FIXTURE_DIR / "info.json"
            if path.exists():
                return json.loads(path.read_text().replace("{base}", paths.fixture_media_base()))
            continue
        path = paths.FIXTURE_DIR / f"{name}.json"
        if path.exists():
            return json.loads(path.read_text())
    raise errors.AppError(code="UNSUPPORTED_SITE", raw=f"no fixture matches {url}")


def has_fixture(url: str) -> bool:
    return any(re.search(pattern, url, re.IGNORECASE) for pattern, _ in _FIXTURE_MATCHERS)


async def _run_worker(
    url: str, cookies: list[str] | None = None
) -> tuple[dict[str, Any], list[str]]:
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
    payload = json.dumps({"url": url, "cookies_from_browser": cookies}).encode()
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


# The last few inspections, so a download can be planned and started without re-extracting.
# Only the fields a filename template can use are kept, not the (potentially huge) raw dict.
_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
CACHE_SIZE = 8
# The Safari popup inspects the page it opens on; reopening it on the same page should be
# instant. Downloads re-extract anyway (see CLAUDE.md gotcha 20), so a cached model is only
# ever used to show and choose, never to fetch.
_BY_URL: dict[str, tuple[str, float]] = {}
REUSE_SECONDS = 15 * 60


def remember(model: dict[str, Any], info: dict[str, Any], cookies: list[str] | None = None) -> str:
    inspect_id = uuid.uuid4().hex[:16]
    _CACHE[inspect_id] = {
        "model": model,
        # The Safari session, if this video needed one: its download needs it too.
        "cookies": cookies,
        "url": model["source_url"],
        "template_info": {
            k: info.get(k) for k in naming.TEMPLATE_FIELDS if info.get(k) is not None
        },
        "chapters": info.get("chapters") or [],
        # In fixture mode the worker is handed the info dict instead of re-extracting.
        "fixture_info": info if paths.fixture_mode() else None,
    }
    _BY_URL[model["source_url"]] = (inspect_id, time.monotonic())
    while len(_CACHE) > CACHE_SIZE:
        _CACHE.popitem(last=False)
    for url in [u for u, (i, _) in _BY_URL.items() if i not in _CACHE]:
        del _BY_URL[url]
    return inspect_id


def _reusable(url: str) -> dict[str, Any] | None:
    inspect_id, at = _BY_URL.get(url, ("", 0.0))
    entry = _CACHE.get(inspect_id)
    if entry is None or time.monotonic() - at > REUSE_SECONDS:
        return None
    if entry.get("cookies") and not settings_store.load().safari_login:
        return None  # inspected with the session, which has been turned off since
    _CACHE.move_to_end(inspect_id)
    model: dict[str, Any] = entry["model"]
    return model


def recall(inspect_id: str) -> dict[str, Any]:
    entry = _CACHE.get(inspect_id)
    if entry is not None:
        _CACHE.move_to_end(inspect_id)  # in use: the last to be evicted
    if entry is None:
        # The server restarted or the entry aged out: the UI re-inspects and tries again.
        raise errors.AppError(code="INSPECT_EXPIRED", raw=inspect_id)
    return entry


async def _extract(url: str) -> tuple[dict[str, Any], list[str], list[str] | None]:
    """Without an account first, always. Only a video that asks for a signed-in account
    (age-restricted, members-only, private) is tried once more with the Safari session."""
    try:
        info, warnings = await _run_worker(url)
        return info, warnings, None
    except errors.AppError as exc:
        session = browser_session.ytdlp_option()
        # YouTube only: the session is a YouTube one, and a "login" in some other site's
        # error must never send it anywhere else.
        if exc.code not in browser_session.AUTH_CODES or session is None:
            raise
        if not browser_session.is_youtube_url(url):
            raise
        if not settings_store.load().safari_login:
            raise
        first = exc.code
    try:
        info, warnings = await _run_worker(url, session)
    except errors.AppError as again:
        if again.code in browser_session.AUTH_CODES:
            # Signed in, and still refused: not signed in to YouTube in Safari, or the account
            # is not age-verified. Say so instead of repeating "sign in".
            raise errors.AppError(
                code="SESSION_NOT_ENOUGH", raw=again.raw, detail={"first": first}
            ) from None
        raise
    return info, [*warnings, "USED_SAFARI_LOGIN"], session


async def inspect(url: str, *, reuse: bool = False) -> dict[str, Any]:
    url = validate_url(url)
    if reuse and (cached := _reusable(url)) is not None:
        return cached
    warnings: list[str] = []
    cookies: list[str] | None = None
    if paths.fixture_mode():
        info = _fixture_for(url)
    else:
        info, warnings, cookies = await _extract(url)
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
    if model["kind"] == "video":
        model["defaults"] = selection.all_defaults(model)
        model["offers"] = offers.build(model)
        model["inspect_id"] = remember(model, info, cookies)
    return model
