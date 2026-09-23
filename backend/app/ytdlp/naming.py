"""Output filenames: yt-dlp's template language, but never outside the chosen root.

Three rules, each learned the hard way:
* A literal ".." in the *template* is the user's mistake and is refused. A "." or ".." that
  comes from a *field* (a video titled "..") is data and is neutralised to "_".
* Every path component is trimmed to MAX_COMPONENT_BYTES so APFS's 255-byte limit is never hit
  after a long download, with room left for " (12)" and ".description.txt".
* A set of files (a video and its sidecars) gets one free base name, reserved atomically with
  O_EXCL placeholders, so two jobs can never claim the same name and sidecars keep matching.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any

from app import errors

TEMPLATE_FIELDS = (
    "id",
    "title",
    "channel",
    "uploader",
    "upload_date",
    "extractor",
    "extractor_key",
    "webpage_url_domain",
    "duration",
    "playlist",
    "playlist_index",
)
MAX_COMPONENT_BYTES = 200
MAX_SUFFIX_BYTES = 48
_UNSAFE_SUFFIX = re.compile(r"[^A-Za-z0-9._-]")


def _ydl(template: str) -> Any:
    import yt_dlp

    return yt_dlp.YoutubeDL({"outtmpl": {"default": template}, "quiet": True, "no_warnings": True})


def validate_template(template: str) -> None:
    import yt_dlp

    template = template.strip()
    if not template or template.startswith(("/", "~")):
        raise errors.AppError(code="INVALID_TEMPLATE", raw=template)
    if any(part.strip() in (".", "..") for part in template.split("/")):
        raise errors.AppError(code="PATH_OUTSIDE_ROOT", raw=template)
    problem = yt_dlp.YoutubeDL.validate_outtmpl(template)
    if problem:
        raise errors.AppError(code="INVALID_TEMPLATE", raw=str(problem))


def trim_bytes(text: str, limit: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", errors="ignore").rstrip()


def safe_component(part: str) -> str:
    part = part.replace("\x00", "").strip()
    if part in ("", ".", ".."):
        return "_"
    if part.startswith("."):
        part = "_" + part[1:]  # a title starting with "." would otherwise be a hidden file
    return trim_bytes(part, MAX_COMPONENT_BYTES) or "_"


def safe_suffix(suffix: str) -> str:
    """Suffixes are built from our own strings plus subtitle/language keys; keep them inert."""
    cleaned = _UNSAFE_SUFFIX.sub("_", suffix)
    if not cleaned.startswith("."):
        cleaned = "." + cleaned
    return trim_bytes(re.sub(r"\.{2,}", ".", cleaned), MAX_SUFFIX_BYTES)


def render_relative(template: str, info: dict[str, Any], ext: str) -> PurePosixPath:
    """Render to a path relative to the download root, *without* its extension."""
    validate_template(template)
    context = {k: info.get(k) for k in TEMPLATE_FIELDS if info.get(k) is not None}
    context["ext"] = ext
    try:
        rendered = _ydl(template).prepare_filename(context)
    except (ValueError, TypeError) as exc:
        raise errors.AppError(code="INVALID_TEMPLATE", raw=str(exc)) from None
    if not rendered:
        raise errors.AppError(code="INVALID_TEMPLATE", raw=template)
    suffix = f".{ext}"
    if rendered.endswith(suffix):
        rendered = rendered[: -len(suffix)]
    return PurePosixPath(*(safe_component(p) for p in rendered.split("/")))


def claim(root: Path, relative_stem: PurePosixPath, suffixes: list[str]) -> list[Path]:
    """Reserve one free base name for a whole set of files; returns the reserved paths.

    Each path is created empty with O_EXCL, so the reservation is atomic: the caller then
    os.replace()s its finished file onto its own placeholder. Never touches an existing file.
    """
    base = root.expanduser().resolve()
    parts = [safe_component(p) for p in relative_stem.parts] or ["_"]
    parent = base.joinpath(*parts[:-1])
    parent.mkdir(parents=True, exist_ok=True)
    real_parent = parent.resolve()
    # A symlinked sub-folder must not lead outside the root either.
    if not real_parent.is_relative_to(base):
        raise errors.AppError(code="PATH_OUTSIDE_ROOT", raw=str(real_parent))
    clean_suffixes = [safe_suffix(s) for s in suffixes]
    for n in range(1, 1000):
        name = parts[-1] if n == 1 else f"{parts[-1]} ({n})"
        targets = [real_parent / f"{name}{suffix}" for suffix in clean_suffixes]
        taken: list[Path] = []
        try:
            for target in targets:
                os.close(os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
                taken.append(target)
            return targets
        except FileExistsError:
            for path in taken:
                path.unlink(missing_ok=True)
    raise errors.AppError(code="PATH_EXHAUSTED", raw=str(real_parent / parts[-1]))


def release(placeholders: list[Path]) -> None:
    """Undo a claim for files that never arrived. Only empty placeholders are removed."""
    for path in placeholders:
        try:
            if path.is_file() and path.stat().st_size == 0:
                path.unlink()
        except OSError:
            continue
