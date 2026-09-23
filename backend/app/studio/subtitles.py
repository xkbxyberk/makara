"""SRT/WebVTT in pure Python: parse, shift, clean YouTube's auto captions, write SRT.

Why not FFmpeg for these: the two operations Berk needs most are *semantic* -- dropping the
rolling duplicate lines of YouTube's speech-recognition captions, and shifting timings -- and
both are easier to get exactly right (and to test) on parsed cues than through filters.
Format conversions that need real styling support (ASS) still go through FFmpeg.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

_TIME = r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})"
_CUE_TIMING = re.compile(rf"^\s*{_TIME}\s*-->\s*{_TIME}")
_TAG = re.compile(r"<[^>]*>")
MIN_CUE_SECONDS = 0.05  # YouTube's 10 ms "hold" cues exist only to keep a line on screen


@dataclass(slots=True)
class Cue:
    start: float
    end: float
    lines: list[str] = field(default_factory=list)


def _seconds(h: str | None, m: str, s: str, ms: str) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse(text: str) -> list[Cue]:
    """Parse SRT or WebVTT. Cue numbers, VTT headers, NOTE/STYLE blocks and settings are ignored."""
    cues: list[Cue] = []
    current: Cue | None = None
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = _CUE_TIMING.match(raw)
        if match:
            g = match.groups()
            current = Cue(_seconds(*g[0:4]), _seconds(*g[4:8]))
            cues.append(current)
            continue
        if raw == "":
            current = None  # an empty line ends a cue
            continue
        if not raw.strip():
            # YouTube starts rolling cues with a " " line right after the timing: still inside
            # the cue. But once a cue has text, a line of spaces or tabs is a separator (plenty
            # of hand-edited SRT files have them) and must end the cue.
            if current is not None and current.lines:
                current = None
            continue
        if current is not None:
            current.lines.append(raw.rstrip())
    return cues


def _stamp(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    h, rest = divmod(total_ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def to_srt(cues: list[Cue]) -> str:
    blocks = []
    for n, cue in enumerate((c for c in cues if c.lines), start=1):
        blocks.append(f"{n}\n{_stamp(cue.start)} --> {_stamp(cue.end)}\n" + "\n".join(cue.lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def shift(cues: list[Cue], seconds: float) -> list[Cue]:
    """Move every cue by `seconds` (negative = earlier). Cues pushed entirely before 0 are
    dropped; one straddling 0 is clipped to start at 0."""
    moved = []
    for cue in cues:
        start, end = cue.start + seconds, cue.end + seconds
        if end <= 0:
            continue
        moved.append(Cue(max(0.0, start), end, list(cue.lines)))
    return moved


def clean_auto_captions(cues: list[Cue]) -> list[Cue]:
    """Undo the "rolling" layout of YouTube speech-recognition captions.

    YouTube shows two lines at a time: each cue repeats the previous line and adds a new one
    (with per-word <timestamp><c> tags), and 10 ms cues hold finished lines on screen. Played
    as-is in a normal player, every sentence appears twice. Here: tags are stripped, hold cues
    dropped, lines already shown by the previous cue removed, and each cue ends when the next
    one starts so nothing overlaps.
    """
    cleaned: list[Cue] = []
    previous_lines: list[str] = []
    for cue in cues:
        lines = [re.sub(r"\s+", " ", _TAG.sub("", line)).strip() for line in cue.lines]
        lines = [line for line in lines if line]
        if cue.end - cue.start < MIN_CUE_SECONDS:
            previous_lines = lines or previous_lines
            continue
        fresh = [line for line in lines if line not in previous_lines]
        previous_lines = lines
        if fresh:
            cleaned.append(Cue(cue.start, cue.end, fresh))
    for current, following in itertools.pairwise(cleaned):
        if following.start > current.start:
            current.end = min(current.end, following.start)
    return cleaned


def looks_like_youtube_auto_captions(text: str) -> bool:
    """Per-word timing tags are the fingerprint of YouTube's ASR WebVTT."""
    return bool(re.search(r"<\d{2}:\d{2}:\d{2}\.\d{3}><c>", text))
