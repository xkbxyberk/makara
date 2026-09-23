from __future__ import annotations

import itertools

from app.studio import subtitles

# The shape of a real YouTube speech-recognition WebVTT: rolling two-line cues with per-word
# timing tags, and 10 ms "hold" cues in between.
YOUTUBE_ASR = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.500 align:start position:0%
 
hello<00:00:00.500><c> world</c><00:00:01.000><c> this</c>

00:00:02.500 --> 00:00:02.510 align:start position:0%
hello world this
 

00:00:02.510 --> 00:00:05.000 align:start position:0%
hello world this
is<00:00:03.000><c> a</c><00:00:03.500><c> test</c>

00:00:05.000 --> 00:00:05.010 align:start position:0%
is a test
 

00:00:05.010 --> 00:00:07.000 align:start position:0%
is a test
of<00:00:05.500><c> captions</c>
"""

SRT = """1
00:00:01,000 --> 00:00:02,500
Merhaba.

2
00:00:03,000 --> 00:00:04,000
İkinci satır
iki satırlı.
"""


def test_parse_srt_and_vtt() -> None:
    cues = subtitles.parse(SRT)
    assert [(c.start, c.end) for c in cues] == [(1.0, 2.5), (3.0, 4.0)]
    assert cues[1].lines == ["İkinci satır", "iki satırlı."]
    assert len(subtitles.parse(YOUTUBE_ASR)) == 5


def test_youtube_rolling_captions_are_cleaned_to_each_line_once() -> None:
    cleaned = subtitles.clean_auto_captions(subtitles.parse(YOUTUBE_ASR))
    assert [c.lines for c in cleaned] == [["hello world this"], ["is a test"], ["of captions"]]
    # No overlaps: each cue ends when the next begins.
    assert all(a.end <= b.start for a, b in itertools.pairwise(cleaned))
    srt = subtitles.to_srt(cleaned)
    assert srt.count("hello world this") == 1
    assert "<c>" not in srt and "00:00:00,500" not in srt


def test_the_fingerprint_detects_youtube_auto_captions_only() -> None:
    assert subtitles.looks_like_youtube_auto_captions(YOUTUBE_ASR)
    assert not subtitles.looks_like_youtube_auto_captions(SRT)


def test_shift_later_and_earlier_with_clipping() -> None:
    cues = subtitles.parse(SRT)
    later = subtitles.shift(cues, 1.5)
    assert [(c.start, c.end) for c in later] == [(2.5, 4.0), (4.5, 5.5)]
    earlier = subtitles.shift(cues, -2.0)
    # The first cue straddles 0 and is clipped; nothing goes negative.
    assert [(c.start, c.end) for c in earlier] == [(0.0, 0.5), (1.0, 2.0)]
    assert subtitles.shift(cues, -10) == []


def test_srt_output_round_trips() -> None:
    cues = subtitles.parse(SRT)
    again = subtitles.parse(subtitles.to_srt(cues))
    assert [(c.start, c.end, c.lines) for c in again] == [(c.start, c.end, c.lines) for c in cues]
    assert "00:00:01,000 --> 00:00:02,500" in subtitles.to_srt(cues)


def test_hours_and_crlf_are_handled() -> None:
    cues = subtitles.parse("1\r\n01:02:03,004 --> 01:02:04,000\r\nx\r\n")
    assert cues[0].start == 3723.004
