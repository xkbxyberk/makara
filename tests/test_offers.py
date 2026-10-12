"""Quick choices come from the video itself. Every row must be downloadable as shown."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app import errors
from app import settings as settings_store
from app.jobs import planning
from app.ytdlp import normalize, offers, selection

FIXTURES = Path(__file__).parent / "fixtures" / "infojson"
VIDEOS = ["youtube_multi_audio", "youtube_many_subs", "other_site"]


def model_for(name: str) -> dict[str, Any]:
    return normalize.normalize(json.loads((FIXTURES / f"{name}.json").read_text()))


def rows_by_id(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    built = offers.build(model)
    return {r["id"]: r for r in [*built["video"], *built["audio"]]}


def test_one_video_row_per_size_frame_rate_and_range_largest_first() -> None:
    built = offers.build(model_for("youtube_multi_audio"))
    ids = [r["id"] for r in built["video"]]
    assert ids == [
        "v1080-24-sdr",
        "v720-24-sdr",
        "v480-24-sdr",
        "v360-24-sdr",
        "v240-24-sdr",
        "v144-24-sdr",
        "v144-12-sdr",
    ]
    assert len(set(ids)) == len(ids)


def test_each_row_is_resolved_for_both_outputs() -> None:
    row = rows_by_id(model_for("youtube_multi_audio"))["v1080-24-sdr"]
    mkv, mp4 = row["outputs"]["mkv"], row["outputs"]["compat_mp4"]
    # The archive keeps the most efficient codec; the compatible file picks what Apple plays.
    assert (mkv["vcodec_label"], mkv["video_step"]) == ("AV1", "copy")
    assert (mp4["vcodec_label"], mp4["video_step"], mp4["audio_steps"]) == (
        "H.264",
        "copy",
        ["copy"],
    )
    # Sizes are video + the original audio, with the usual exact/estimated confidence.
    assert mkv["size"]["bytes"] and mkv["size"]["kind"] in ("exact", "approx", "estimated")


def test_a_size_with_no_compatible_variant_says_it_will_re_encode() -> None:
    row = rows_by_id(model_for("youtube_multi_audio"))["v144-12-sdr"]
    assert row["outputs"]["compat_mp4"]["vcodec_label"] == "VP9"
    assert row["outputs"]["compat_mp4"]["video_step"] == "transcode"
    assert row["outputs"]["mkv"]["video_step"] == "copy"


def test_ai_upscaled_sizes_are_flagged_and_never_recommended() -> None:
    model = model_for("youtube_many_subs")
    rows = rows_by_id(model)
    assert rows["v720-30-sdr"]["ai_upscaled"] and rows["v360-30-sdr"]["ai_upscaled"]
    assert not rows["v240-30-sdr"]["ai_upscaled"]
    recommended = [
        r["id"]
        for r in rows.values()
        if r["kind"] == "video" and r["outputs"]["mkv"]["recommended"]
    ]
    assert recommended == ["v240-30-sdr"]


@pytest.mark.parametrize("output", ["mkv", "compat_mp4"])
@pytest.mark.parametrize("name", VIDEOS)
def test_the_recommended_row_is_exactly_todays_two_click_default(name: str, output: str) -> None:
    """Without a rule, one click downloads what two clicks do today -- in either output."""
    model = model_for(name)
    picked = offers.match(offers.build(model), None, output)
    assert picked is not None and picked["output"] == output
    resolved = offers.resolve(model, picked["offer_id"], picked["output"])
    default = selection.default_selection(model, output)
    assert {k: resolved[k] for k in default} == default


def test_audio_rows_copy_what_the_source_has_and_offer_conversions() -> None:
    rows = offers.build(model_for("youtube_multi_audio"))["audio"]
    assert [(r["id"], r["step"]) for r in rows] == [
        ("a-m4a", "copy"),
        ("a-opus", "copy"),
        ("a-mp3", "transcode"),
    ]
    m4a = rows[0]
    assert m4a["source_codec_label"] == "AAC" and m4a["size"]["kind"] == "exact"
    # A conversion's size is unknown until it runs; it is never guessed.
    assert rows[2]["size"]["bytes"] is None


def test_audio_from_an_unknown_codec_is_probed_not_promised() -> None:
    rows = offers.build(model_for("other_site"))["audio"]
    assert rows and {r["step"] for r in rows} == {"probe"}


def test_a_playlist_offers_nothing() -> None:
    model = normalize.normalize(json.loads((FIXTURES / "youtube_playlist_flat.json").read_text()))
    assert offers.build(model) == {"video": [], "audio": []}
    assert offers.match(offers.build(model), None, "mkv") is None


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ({"kind": "video", "height": 720, "output": "compat_mp4"}, ("v720-24-sdr", "compat_mp4")),
        # No 1440p here: the nearest smaller size, never a larger one.
        ({"kind": "video", "height": 1440}, ("v1080-24-sdr", "mkv")),
        ({"kind": "video", "height": 600, "output": "mkv"}, ("v480-24-sdr", "mkv")),
        # Nothing smaller exists: then the smallest larger one.
        ({"kind": "video", "height": 100}, ("v144-24-sdr", "mkv")),
        # Same size, closest frame rate.
        ({"kind": "video", "height": 144, "fps": 12}, ("v144-12-sdr", "mkv")),
        ({"kind": "audio", "format": "opus"}, ("a-opus", None)),
        ({"kind": "audio", "format": "mp3"}, ("a-mp3", None)),
    ],
)
def test_a_remembered_rule_maps_to_the_closest_row(
    rule: dict[str, Any], expected: tuple[str, str | None]
) -> None:
    picked = offers.match(offers.build(model_for("youtube_multi_audio")), rule, "mkv")
    assert picked is not None
    assert (picked["offer_id"], picked["output"]) == expected


def test_a_rule_skips_ai_upscales_when_a_real_size_exists() -> None:
    picked = offers.match(
        offers.build(model_for("youtube_many_subs")), {"kind": "video", "height": 1080}, "mkv"
    )
    assert picked == {"offer_id": "v240-30-sdr", "output": "mkv"}


def test_without_a_rule_the_default_mode_decides_video_or_audio() -> None:
    built = offers.build(model_for("youtube_multi_audio"))
    assert offers.match(built, None, "compat_mp4") == {
        "offer_id": "v1080-24-sdr",
        "output": "compat_mp4",
    }
    picked = offers.match(built, None, "audio")
    assert picked is not None and picked["offer_id"].startswith("a-")


def test_choosing_another_language_takes_that_languages_track() -> None:
    model = model_for("youtube_multi_audio")
    german = next(g for g in model["audio_languages"] if g["language"].startswith("de"))
    chosen = offers.resolve(model, "v1080-24-sdr", "mkv", audio_language=german["language"])
    german_ids = {t["format_id"] for t in german["tracks"]}
    assert chosen["audio_format_ids"] and set(chosen["audio_format_ids"]) <= german_ids
    audio = offers.resolve(model, "a-m4a", None, audio_language=german["language"])
    assert audio["mode"] == "audio" and audio["audio_codec"] == "m4a"
    assert set(audio["audio_format_ids"]) <= german_ids


def test_rules_round_trip_through_their_rows() -> None:
    rows = rows_by_id(model_for("youtube_multi_audio"))
    assert offers.rule_for(rows["v720-24-sdr"], "compat_mp4") == {
        "kind": "video",
        "height": 720,
        "fps": 24,
        "hdr": False,
        "output": "compat_mp4",
    }
    assert offers.rule_for(rows["a-opus"], None) == {"kind": "audio", "format": "opus"}


@pytest.mark.parametrize("name", VIDEOS)
def test_every_row_and_output_plans_cleanly_and_as_promised(name: str) -> None:
    """The row's promise (copy vs re-encode) is what the planner will actually do."""
    model = model_for(name)
    entry = {
        "model": model,
        "url": "https://example.test/x",
        "template_info": {"title": "t", "id": "x", "extractor_key": "Youtube"},
    }
    settings = settings_store.Settings()
    built = offers.build(model)
    for row in built["video"]:
        for output, promised in row["outputs"].items():
            chosen = offers.resolve(model, row["id"], output)
            assert chosen == promised["selection"]  # what the panel applies is what is queued
            preview = planning.plan(entry, chosen, settings)
            assert not preview["blocking"], (row["id"], output, preview["notices"])
            assert preview["plan"]["video"] == promised["video_step"], (row["id"], output)
            assert preview["size"] == promised["size"]
    for row in built["audio"]:
        chosen = offers.resolve(model, row["id"], None)
        assert chosen == row["selection"]
        preview = planning.plan(entry, chosen, settings)
        assert not preview["blocking"], (row["id"], preview["notices"])
        assert preview["plan"]["audio"] == [row["step"]], row["id"]


@pytest.mark.parametrize("name", VIDEOS)
def test_a_conversion_starts_from_the_same_track_as_the_audio_default(name: str) -> None:
    model = model_for(name)
    default = selection.default_selection(model, "audio")["audio_format_ids"]
    mp3 = next(r for r in offers.build(model)["audio"] if r["format"] == "mp3")
    assert [mp3["format_id"]] == default


def test_an_unknown_audio_language_is_refused_never_swapped_for_the_original() -> None:
    model = model_for("youtube_multi_audio")
    with pytest.raises(errors.AppError) as caught:
        offers.resolve(model, "v1080-24-sdr", "mkv", audio_language="xx")
    assert caught.value.code == "AUDIO_LANGUAGE_UNKNOWN"
    with pytest.raises(errors.AppError):
        offers.resolve(model, "a-m4a", None, audio_language="xx")
    # A bare language code finds its regional track ("en" -> "en-US").
    chosen = offers.resolve(model, "v1080-24-sdr", "mkv", audio_language="en")
    original = selection.primary_audio_group(model)
    assert original is not None
    assert set(chosen["audio_format_ids"]) <= {t["format_id"] for t in original["tracks"]}


def test_a_video_row_badges_an_audio_re_encode_too() -> None:
    """MP4 with no AAC to copy: the picture is copied but the sound is converted -- say so."""
    model = model_for("youtube_many_subs")
    for group in model["audio_languages"]:
        group["tracks"] = [t for t in group["tracks"] if t.get("acodec_label") != "AAC"]
    out = rows_by_id(model)["v240-30-sdr"]["outputs"]["compat_mp4"]
    assert out["video_step"] == "copy" and "transcode" in out["audio_steps"]
    assert out["step"] == "transcode"


def test_audio_inside_a_muxed_file_never_shows_the_whole_file_as_its_size() -> None:
    model = model_for("other_site")
    for fmt in model["muxed_formats"]:
        fmt["acodec"], fmt["acodec_label"] = "mp4a.40.2", "AAC"
    m4a = next(r for r in offers.build(model)["audio"] if r["format"] == "m4a")
    assert m4a["step"] == "copy" and m4a["size"]["bytes"] is None


def test_a_size_prefers_video_only_plus_the_original_track_over_a_muxed_file() -> None:
    model = model_for("youtube_multi_audio")
    out = rows_by_id(model)["v360-24-sdr"]["outputs"]["compat_mp4"]
    picked = next(f for f in model["video_formats"] if f["format_id"] == out["video_format_id"])
    assert not picked["has_audio"] and out["selection"]["audio_format_ids"]
    assert out["audio_steps"] == ["copy"]


def test_audio_only_defaults_match_the_panel() -> None:
    built = offers.build(model_for("youtube_multi_audio"))
    assert offers.match(built, None, "audio") == {"offer_id": "a-mp3", "output": None}
    rows = {r["id"]: r for r in built["audio"]}
    assert rows["a-mp3"]["selection"]["audio_quality"] == selection.DEFAULT_AUDIO_QUALITY
    assert rows["a-m4a"]["selection"]["audio_quality"] is None  # a copy has no quality


def test_a_row_of_unknown_size_never_beats_a_known_one() -> None:
    model = model_for("other_site")
    model["muxed_formats"][-1]["height"] = None
    built = offers.build(model)
    assert any(r["height"] is None for r in built["video"])
    picked = offers.match(built, {"kind": "video", "height": 100}, "mkv")
    assert picked is not None
    row = next(r for r in built["video"] if r["id"] == picked["offer_id"])
    assert row["height"] is not None
