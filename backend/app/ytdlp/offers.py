"""Quick choices: what this video actually offers, as one-click rows.

No fixed profiles (Berk's decision). The rows come from the inspected video: one video row per
distinct resolution / frame rate / dynamic range, each resolved for both outputs (archive MKV
and compatible MP4), plus audio-only rows. Each row says what it will cost (size) and whether
anything is re-encoded, and resolves to the same kind of selection the full track picker sends,
so the download panel, the Safari extension and the queue can never disagree.

A *rule* is the remembered shape of a choice ("1080p, MKV") that carries over to the next
video; `match` finds the closest row of another video for it.
"""

from __future__ import annotations

from typing import Any

from app import errors
from app.ytdlp import compat, normalize, selection
from app.ytdlp.selection import codec_family

OUTPUTS = ("mkv", "compat_mp4")
# Audio-only targets, and the source codecs each one keeps without re-encoding.
AUDIO_TARGETS = {"opus": {"opus"}, "m4a": {"mp4a", "aac"}, "mp3": {"mp3"}}
# Shown as conversions when the source has no stream that copies into them.
CONVERSIONS = ("m4a", "mp3")
STEP_ORDER = {"copy": 0, "probe": 1, "transcode": 2}

UNKNOWN_SIZE = {"bytes": None, "kind": normalize.SIZE_UNKNOWN, "unreliable": False, "missing": 1}


def build(model: dict[str, Any]) -> dict[str, Any]:
    if model.get("kind") != "video":
        return {"video": [], "audio": []}
    return {"video": _video_rows(model), "audio": _audio_rows(model)}


# ---- video ---------------------------------------------------------------------------------


def _video_candidates(model: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [*model.get("video_formats", []), *model.get("muxed_formats", [])]
    return [f for f in rows if f.get("drm") != "yes"]


def _hdr(fmt: dict[str, Any]) -> bool:
    return fmt.get("dynamic_range") not in (None, "SDR")


def _group_key(fmt: dict[str, Any]) -> tuple[int, int, bool]:
    return (fmt.get("height") or 0, round(fmt.get("fps") or 0), _hdr(fmt))


def _video_rows(model: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = {o: selection.default_selection(model, o)["video_format_id"] for o in OUTPUTS}
    groups: dict[tuple[int, int, bool], list[dict[str, Any]]] = {}
    for fmt in _video_candidates(model):
        groups.setdefault(_group_key(fmt), []).append(fmt)
    rows = []
    for key in sorted(groups, key=lambda k: (-k[0], -k[1], not k[2])):
        group = groups[key]
        height, fps, hdr = key
        outputs = {output: _resolve_video(model, group, output) for output in OUTPUTS}
        for output, resolved in outputs.items():
            # What "two clicks" downloads today in this output: preselected without a rule.
            resolved["recommended"] = resolved["video_format_id"] == defaults[output]
        rows.append(
            {
                "id": f"v{height}-{fps}-{'hdr' if hdr else 'sdr'}",
                "kind": "video",
                "height": height or None,
                "fps": fps or None,
                "dynamic_range": outputs["mkv"]["format"].get("dynamic_range"),
                # Every variant at this size is YouTube's AI upscale: say so, never hide it.
                "ai_upscaled": all(selection._variant_penalty(f) for f in group),
                "outputs": {
                    output: {k: v for k, v in resolved.items() if k != "format"}
                    for output, resolved in outputs.items()
                },
                "rule": {"kind": "video", "height": height or None, "fps": fps or None, "hdr": hdr},
            }
        )
    return rows


def _resolve_video(
    model: dict[str, Any], group: list[dict[str, Any]], output: str
) -> dict[str, Any]:
    """The best variant of one size for one output, its audio, cost and re-encode plan."""
    # A muxed file's bitrate includes its sound, so it would outrank the video-only stream of
    # the same size -- and bring a lesser, unchosen audio. With real audio tracks to add, the
    # video-only streams are the candidates.
    video_only = [f for f in group if not f.get("has_audio")]
    if video_only and selection.primary_audio_group(model):
        group = video_only
    restricted = {**model, "video_formats": group, "muxed_formats": []}
    video = selection.pick_video(restricted, output)
    assert video is not None  # the group is never empty
    chosen = _video_selection(model, video, output, None, None)
    advice = compat.advise(
        model,
        mode=output,
        video_format_id=video["format_id"],
        audio_format_ids=chosen["audio_format_ids"],
        subtitle_keys=[],
    )
    steps = [advice["plan"]["video"], *advice["plan"]["audio"]]
    return {
        "format": video,
        # Ready to queue as is (original audio, default subtitles): what the panel applies.
        "selection": chosen,
        "video_format_id": video["format_id"],
        "vcodec_label": video.get("vcodec_label"),
        "size": normalize.estimate_total_size(
            model, [video["format_id"], *chosen["audio_format_ids"]]
        ),
        "video_step": advice["plan"]["video"],
        "audio_steps": advice["plan"]["audio"],
        # The heaviest thing that happens to any track: what the row's badge says.
        "step": max((s for s in steps if s), key=STEP_ORDER.__getitem__, default="copy"),
        "hdr_tonemap": output == "compat_mp4"
        and advice["plan"]["video"] == "transcode"
        and _hdr(video),
    }


def _audio_group(model: dict[str, Any], language: str | None) -> dict[str, Any] | None:
    """The group for a language, or the original when none is asked for. An asked-for language
    that this video does not have is an error, never a silent switch to another language."""
    groups = model.get("audio_languages") or []
    if not language:
        return selection.primary_audio_group(model)
    exact = [g for g in groups if g["language"] == language]
    base = language.split("-")[0].lower()
    same_base = [g for g in groups if (g["language"] or "").split("-")[0].lower() == base]
    group = (exact or same_base or [None])[0]
    if group is None or not [t for t in group.get("tracks", []) if t.get("drm") != "yes"]:
        raise errors.AppError(code="AUDIO_LANGUAGE_UNKNOWN", raw=language)
    return group


def _video_selection(
    model: dict[str, Any],
    video: dict[str, Any],
    output: str,
    language: str | None,
    subtitle_keys: list[str] | None,
) -> dict[str, Any]:
    audio = _audio_for(model, video, output, language)
    return {
        "mode": output,
        "video_format_id": video["format_id"],
        "audio_format_ids": [audio["format_id"]] if audio else [],
        "subtitle_keys": selection.default_subtitles(model)
        if subtitle_keys is None
        else list(subtitle_keys),
        "audio_codec": None,
        "audio_quality": None,
    }


def _audio_for(
    model: dict[str, Any], video: dict[str, Any], output: str, language: str | None
) -> dict[str, Any] | None:
    # A muxed format already carries its sound; adding another track would double it.
    if video.get("has_audio") and not language:
        return None
    group = _audio_group(model, language)
    return selection.pick_audio_track(group, output) if group else None


# ---- audio only ----------------------------------------------------------------------------


def _audio_sources(model: dict[str, Any], language: str | None) -> list[dict[str, Any]]:
    group = _audio_group(model, language)
    tracks = [t for t in (group or {}).get("tracks", []) if t.get("drm") != "yes"]
    if tracks:
        return tracks
    # Sites like archive.org only offer audio inside a muxed file; extract from that.
    return [f for f in _video_candidates(model) if f.get("has_audio")]


def _source_for(sources: list[dict[str, Any]], target: str) -> tuple[dict[str, Any] | None, bool]:
    """The track to extract `target` from, and whether it is copied (no re-encode)."""
    copyable = [t for t in sources if codec_family(t.get("acodec")) in AUDIO_TARGETS[target]]
    if copyable:
        best = max(
            copyable,
            key=lambda t: (
                -selection._variant_penalty(t),
                not t.get("is_manifest"),
                t.get("abr") or t.get("tbr") or 0,
            ),
        )
        return best, True
    # A conversion starts from the same track today's audio-only default uses.
    return selection.pick_audio_track({"tracks": sources}, "audio"), False


def _audio_selection(model: dict[str, Any], target: str, language: str | None) -> dict[str, Any]:
    source, copied = _source_for(_audio_sources(model, language), target)
    return {
        "mode": "audio",
        "video_format_id": None,
        "audio_format_ids": [source["format_id"]] if source else [],
        "subtitle_keys": [],
        "audio_codec": target,
        # A copy has no quality to choose; a conversion uses the panel's default.
        "audio_quality": None if copied else selection.DEFAULT_AUDIO_QUALITY,
    }


def _audio_rows(model: dict[str, Any]) -> list[dict[str, Any]]:
    sources = _audio_sources(model, None)
    muxed = {f["format_id"] for f in _video_candidates(model)}
    copies: list[dict[str, Any]] = []
    conversions: list[dict[str, Any]] = []
    for target in AUDIO_TARGETS:
        source, copied = _source_for(sources, target)
        if source is None or (not copied and target not in CONVERSIONS):
            continue
        # The size of a stream that is only audio. A muxed file's size is the whole video,
        # and a conversion's size is only known once it has run: neither is ever shown.
        audio_only = source["format_id"] not in muxed
        row = {
            "id": f"a-{target}",
            "kind": "audio",
            "format": target,
            "format_id": source["format_id"],
            "source_codec_label": source.get("acodec_label"),
            "abr": source.get("abr") if copied else None,
            # An unknown source codec is probed by the worker: it may still be a plain copy.
            "step": "copy" if copied else ("probe" if not source.get("acodec") else "transcode"),
            "size": normalize.estimate_total_size(model, [source["format_id"]])
            if copied and audio_only
            else UNKNOWN_SIZE,
            "rule": {"kind": "audio", "format": target},
            "selection": _audio_selection(model, target, None),
        }
        (copies if copied else conversions).append(row)
    copies.sort(key=lambda r: -(r["abr"] or 0))
    return copies + conversions


# ---- choosing --------------------------------------------------------------------------------


def _output(value: str | None, default_mode: str) -> str:
    for candidate in (value, default_mode):
        if candidate in OUTPUTS:
            return str(candidate)
    return "mkv"


def match(
    offers: dict[str, Any], rule: dict[str, Any] | None, default_mode: str
) -> dict[str, Any] | None:
    """The row (and output) a remembered rule picks in this video, or today's default."""
    video, audio = offers.get("video") or [], offers.get("audio") or []
    if not video and not audio:
        return None
    rule = rule or {}
    kind = rule.get("kind") or ("audio" if default_mode == "audio" else "video")
    if kind == "audio" or not video:
        if not audio:
            return {"offer_id": video[0]["id"], "output": _output(None, default_mode)}
        wanted = rule.get("format") or selection.DEFAULT_AUDIO_CODEC
        row = next((r for r in audio if r["format"] == wanted), audio[0])
        return {"offer_id": row["id"], "output": None}
    output = _output(rule.get("output"), default_mode)
    height = rule.get("height")
    if not height:
        row = next((r for r in video if r["outputs"][output]["recommended"]), video[0])
        return {"offer_id": row["id"], "output": output}
    # An AI upscale is never a better match than a real size, unless it is all there is; a
    # row of unknown size only when no size is known at all.
    real = [r for r in video if not r["ai_upscaled"]] or video
    sized = [r for r in real if r["height"]] or real
    # The same size if it exists; otherwise the nearest smaller one (a 720p rule is usually
    # about file size), and only then the smallest larger one.
    heights = sorted({r["height"] or 0 for r in sized})
    lower = [h for h in heights if h <= height]
    target = max(lower) if lower else min(heights)
    same = [r for r in sized if (r["height"] or 0) == target]
    fps, hdr = rule.get("fps"), bool(rule.get("hdr"))
    # Rows are best-first, and min() keeps the first of equals: without a remembered frame
    # rate the smoothest one at that size wins.
    row = min(
        same,
        key=lambda r: (r["rule"]["hdr"] != hdr, abs((r["fps"] or 0) - fps) if fps else 0),
    )
    return {"offer_id": row["id"], "output": output}


def resolve(
    model: dict[str, Any],
    offer_id: str,
    output: str | None,
    audio_language: str | None = None,
    subtitle_keys: list[str] | None = None,
    default_mode: str = "mkv",
) -> dict[str, Any]:
    """Turn a row into the selection the track picker would send. Raises KeyError if the row
    does not exist in this video, AppError for a language it does not have."""
    offers = build(model)
    rows = {r["id"]: r for r in [*offers["video"], *offers["audio"]]}
    row = rows[offer_id]
    if row["kind"] == "audio":
        return _audio_selection(model, row["format"], audio_language)
    output = _output(output, default_mode)
    video = compat.index_formats(model)[row["outputs"][output]["video_format_id"]]
    return _video_selection(model, video, output, audio_language, subtitle_keys)


def rule_for(row: dict[str, Any], output: str | None) -> dict[str, Any]:
    rule = dict(row["rule"])
    if row["kind"] == "video":
        rule["output"] = _output(output, "mkv")
    return rule
