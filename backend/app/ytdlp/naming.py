"""Output filenames: yt-dlp's template language, but never allowed outside the chosen root."""

from __future__ import annotations

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


def _ydl(template: str) -> Any:
    import yt_dlp

    return yt_dlp.YoutubeDL({"outtmpl": {"default": template}, "quiet": True, "no_warnings": True})


def validate_template(template: str) -> None:
    import yt_dlp

    template = template.strip()
    if not template or template.startswith(("/", "~")):
        raise errors.AppError(code="INVALID_TEMPLATE", raw=template)
    problem = yt_dlp.YoutubeDL.validate_outtmpl(template)
    if problem:
        raise errors.AppError(code="INVALID_TEMPLATE", raw=str(problem))


def render_relative(template: str, info: dict[str, Any], ext: str) -> PurePosixPath:
    """Render to a path relative to the download root, *without* its extension."""
    validate_template(template)
    context = {k: info.get(k) for k in TEMPLATE_FIELDS if info.get(k) is not None}
    context["ext"] = ext
    rendered = _ydl(template).prepare_filename(context)
    if not rendered:
        raise errors.AppError(code="INVALID_TEMPLATE", raw=template)
    path = PurePosixPath(rendered)
    if path.is_absolute() or any(part in ("..", ".", "") for part in path.parts):
        raise errors.AppError(code="PATH_OUTSIDE_ROOT", raw=rendered)
    suffix = f".{ext}"
    return path.with_name(path.name[: -len(suffix)]) if path.name.endswith(suffix) else path


def resolve_inside(root: Path, relative: PurePosixPath) -> Path:
    base = root.expanduser().resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base):
        raise errors.AppError(code="PATH_OUTSIDE_ROOT", raw=str(target))
    return target


def unique(path: Path) -> Path:
    """Never overwrite: "name.mkv" becomes "name (2).mkv" if the first one exists."""
    if not path.exists():
        return path
    for n in range(2, 1000):
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise errors.AppError(code="PATH_EXHAUSTED", raw=str(path))
