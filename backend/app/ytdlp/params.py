"""Shared YoutubeDL parameters and JS-runtime discovery.

Two facts drive this module:
* `js_runtimes` is a *top-level* YoutubeDL param, and passing a dict REPLACES the
  default (which is deno-only). See the yt-dlp README, "Embedding yt-dlp".
* The API defaults differ from the CLI defaults: `ignoreerrors` is False and
  `extract_flat` is False here, unlike on the command line.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

# Highest priority first, matching yt-dlp's own ordering.
RUNTIME_ORDER = ("deno", "node", "quickjs", "bun")
_VERSION_ARG = {"deno": "--version", "node": "--version", "bun": "--version", "quickjs": "--help"}
_EXECUTABLE = {"quickjs": "qjs"}


@dataclass(frozen=True, slots=True)
class JsRuntime:
    name: str
    path: str
    version: str


def find_js_runtimes() -> list[JsRuntime]:
    """Every supported JS runtime on PATH, best first."""
    found: list[JsRuntime] = []
    for name in RUNTIME_ORDER:
        path = shutil.which(_EXECUTABLE.get(name, name))
        if not path:
            continue
        found.append(JsRuntime(name=name, path=path, version=_probe_version(path, name)))
    return found


def _probe_version(path: str, name: str) -> str:
    try:
        # Fixed argv, never a shell string.
        out = subprocess.run(
            [path, _VERSION_ARG[name]], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    text = (out.stdout or out.stderr).strip()
    return text.splitlines()[0] if text else "unknown"


def js_runtimes_param(runtimes: list[JsRuntime] | None = None) -> dict[str, dict[str, str]]:
    """Enable every runtime we actually found, pinned to its absolute path.

    Pinning the path matters because the app may be launched from Finder, where PATH
    is the bare login PATH and Homebrew's bin directory is missing.
    """
    runtimes = find_js_runtimes() if runtimes is None else runtimes
    return {r.name: {"path": r.path} for r in runtimes} or {"deno": {}}


def base_params(*, ffmpeg_location: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "skip_download": True,
        "js_runtimes": js_runtimes_param(),
        # Any truthy value here makes yt-dlp *report* extraction errors and return None instead
        # of raising -- which would turn every geo/login/DRM failure into "video unavailable".
        "ignoreerrors": False,
    }
    if ffmpeg_location:
        params["ffmpeg_location"] = ffmpeg_location
    return params


def inspect_params(*, ffmpeg_location: str | None = None) -> dict[str, Any]:
    params = base_params(ffmpeg_location=ffmpeg_location)
    params.update(
        {
            # A watch URL that also names a playlist means "this video"; a playlist or channel
            # URL is listed flat, otherwise a big channel would extract every video in turn.
            "noplaylist": True,
            "extract_flat": "in_playlist",
            # Both flags are what make yt-dlp build the machine-translated caption list.
            "writesubtitles": True,
            "writeautomaticsub": True,
        }
    )
    return params
