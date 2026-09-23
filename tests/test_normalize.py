"""Normalisation is the contract every screen depends on, so it is tested hard."""

from __future__ import annotations

from typing import Any

from app.ytdlp.normalize import (
    audio_role,
    classify_automatic_caption,
    estimate_total_size,
    format_kind,
    normalize,
    normalize_subtitles,
)


def test_audio_roles_come_only_from_language_preference() -> None:
    assert audio_role({"language_preference": 10}) == "original"
    assert audio_role({"language_preference": 5}) == "default"
    assert audio_role({"language_preference": -1}) == "dub"
    assert audio_role({"language_preference": -10}) == "descriptive"
    assert audio_role({"language": "en-desc", "language_preference": -1}) == "descriptive"
    assert audio_role({}) == "unknown"


def test_format_kind_treats_none_and_unknown_codecs_differently() -> None:
    assert format_kind({"vcodec": "none", "acodec": "opus"}) == "audio"
    assert format_kind({"vcodec": "vp9", "acodec": "none"}) == "video"
    assert format_kind({"vcodec": "avc1", "acodec": "mp4a"}) == "muxed"
    assert format_kind({"vcodec": "none", "acodec": "none"}) == "storyboard"
    assert format_kind({"ext": "mhtml", "vcodec": "none", "acodec": "none"}) == "storyboard"
    # archive.org reports neither codec but does report geometry.
    assert format_kind({"vcodec": None, "acodec": None, "height": 300}) == "muxed"
    assert format_kind({"vcodec": None, "acodec": None}) == "audio"
    # A known picture codec with unknown sound must not be advertised as carrying audio.
    assert format_kind({"vcodec": "avc1", "acodec": None, "height": 720}) == "video"


def test_multi_audio_groups_by_language_original_first(multi_audio: dict[str, Any]) -> None:
    model = normalize(multi_audio)
    assert model["kind"] == "video"
    groups = model["audio_languages"]
    assert len(groups) == 24
    assert groups[0]["language"] == "en-US"
    assert groups[0]["role"] == "original"
    assert {g["role"] for g in groups[1:]} == {"dub"}
    assert any(g["language"] == "tr" for g in groups)
    # Every track keeps its final, de-duplicated format_id -- never a bare itag.
    ids = [t["format_id"] for g in groups for t in g["tracks"]]
    assert len(ids) == len(set(ids))


def test_single_audio_language_is_not_labelled_a_dub(many_subs: dict[str, Any]) -> None:
    model = normalize(many_subs)
    groups = model["audio_languages"]
    assert len(groups) == 1
    assert groups[0]["role"] == "unknown"
    assert all(track["role"] == "unknown" for track in groups[0]["tracks"])


def test_video_formats_are_sorted_best_first(multi_audio: dict[str, Any]) -> None:
    model = normalize(multi_audio)
    heights = [f["height"] or 0 for f in model["video_formats"]]
    assert heights == sorted(heights, reverse=True)
    assert model["video_formats"][0]["vcodec_label"] in {"H.264", "VP9", "AV1"}


def test_subtitles_split_into_three_kinds(many_subs: dict[str, Any]) -> None:
    subs = normalize_subtitles(many_subs)
    assert len(subs["manual"]) == 64
    assert all(row["kind"] == "manual" for row in subs["manual"])
    # Speech recognition only produces the spoken language. Exactly these two keys are ASR.
    assert {row["key"] for row in subs["auto"]} == {"en", "en-orig"}
    assert subs["auto_translated"], "machine translations must be separated out"
    assert all(row["kind"] == "auto_translated" for row in subs["auto_translated"])
    # These arrive as bare HLS playlists with no tlang= and no name -- still translations.
    translated = {row["key"] for row in subs["auto_translated"]}
    assert {"ckb", "fr-CA", "inh", "pt-BR", "zh-CN", "zh-TW"} <= translated
    # A manual language must never be silently reclassified as automatic.
    assert {row["language"] for row in subs["manual"]} & {"tr", "en"} == {"tr", "en"}


def test_auto_track_that_collides_with_a_manual_key_is_marked_shadowed(
    many_subs: dict[str, Any],
) -> None:
    auto = {row["key"]: row for row in normalize_subtitles(many_subs)["auto"]}
    assert auto["en"]["shadowed_by_manual"] is True
    assert auto["en-orig"]["shadowed_by_manual"] is False


def test_classify_automatic_caption_rules() -> None:
    orig = [{"url": "https://x/api/timedtext?v=A&kind=asr&lang=en", "name": "English (Original)"}]
    assert classify_automatic_caption("en-orig", orig) == ("auto", "en", None)

    translated = [
        {
            "url": "https://x/api/timedtext?v=A&lang=af&tlang=ab-af",
            "name": "Abkhazian from Afrikaans",
        }
    ]
    assert classify_automatic_caption("ab-af", translated) == ("auto_translated", "ab-af", "af")

    self_translated = [
        {"url": "https://x/api/timedtext?v=A&lang=af", "name": "Afrikaans from Afrikaans"}
    ]
    assert classify_automatic_caption("af-af", self_translated)[0] == "auto_translated"

    asr = [{"url": "https://x/hls_timedtext_playlist/caps%3Dasr/index.m3u8", "name": None}]
    assert classify_automatic_caption("tr", asr) == ("auto", "tr", None)


def test_live_chat_is_never_shown_as_a_subtitle() -> None:
    subs = normalize_subtitles(
        {
            "subtitles": {
                "en": [{"ext": "vtt", "url": "https://x?lang=en", "name": "English"}],
                "live_chat": [{"ext": "json", "url": "https://x", "protocol": "youtube_live_chat"}],
            }
        }
    )
    assert [row["language"] for row in subs["manual"]] == ["en"]
    assert subs["has_live_chat"] is True


def test_size_tiers_and_manifest_flags(multi_audio: dict[str, Any]) -> None:
    model = normalize(multi_audio)
    rows = [*model["video_formats"], *[t for g in model["audio_languages"] for t in g["tracks"]]]
    kinds = {row["filesize_kind"] for row in rows}
    assert kinds & {"exact", "estimated"}
    for row in rows:
        if row["filesize_kind"] == "exact":
            assert row["filesize_unreliable"] is False
        if row["filesize_unreliable"]:
            assert row["is_manifest"] and row["filesize_kind"] == "estimated"


def test_estimate_total_size_sums_the_selection(multi_audio: dict[str, Any]) -> None:
    model = normalize(multi_audio)
    video = next(f for f in model["video_formats"] if f["filesize_kind"] == "exact")
    audio = next(t for t in model["audio_languages"][0]["tracks"] if t["filesize"])
    total = estimate_total_size(model, [video["format_id"], audio["format_id"]])
    assert total["bytes"] == video["filesize"] + audio["filesize"]
    assert total["missing"] == 0
    assert estimate_total_size(model, ["nope"])["kind"] == "unknown"


def test_estimate_with_an_unknown_part_is_a_lower_bound() -> None:
    model = {
        "video_formats": [
            {"format_id": "v", "filesize": 1000, "filesize_kind": "exact"},
            {"format_id": "x", "filesize": None, "filesize_kind": "unknown"},
        ]
    }
    total = estimate_total_size(model, ["v", "x"])
    assert total == {"bytes": 1000, "kind": "partial", "unreliable": False, "missing": 1}


def test_estimate_survives_a_malformed_model() -> None:
    malformed = {"video_formats": None, "audio_languages": [{"language": "en"}]}
    assert estimate_total_size(malformed, ["a"])["kind"] == "unknown"


def test_multi_video_is_listed_not_rendered_as_an_empty_video() -> None:
    model = normalize({"_type": "multi_video", "id": "m", "entries": [{"id": "a", "title": "A"}]})
    assert model["kind"] == "playlist"
    assert model["entries"][0]["title"] == "A"


def test_chapters_heatmap_and_thumbnails_survive(multi_audio: dict[str, Any]) -> None:
    model = normalize(multi_audio)
    assert len(model["chapters"]) == 7
    assert len(model["heatmap"]) == 100
    assert all(0 <= (point["value"] or 0) <= 1 for point in model["heatmap"])
    widths = [t["width"] or 0 for t in model["thumbnails"]]
    assert widths == sorted(widths, reverse=True)


def test_playlist_is_a_different_shape(playlist: dict[str, Any]) -> None:
    model = normalize(playlist)
    assert model["kind"] == "playlist"
    assert len(model["entries"]) == 12
    assert model["entries"][0]["title"]
    assert "PLAYLIST_TRACKS_NEED_PER_VIDEO_INSPECT" in model["warnings"]


def test_non_youtube_site_with_unknown_codecs(other_site: dict[str, Any]) -> None:
    model = normalize(other_site)
    assert model["kind"] == "video"
    # Unknown codecs plus a resolution means "muxed", not "dropped".
    assert len(model["muxed_formats"]) == 3
    assert model["video_formats"] == []
    assert model["subtitles"]["manual"] == []
