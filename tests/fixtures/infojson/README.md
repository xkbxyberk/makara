# Recorded yt-dlp info dicts

Captured once with `uv run python scripts/capture_fixtures.py` on 2026-09-23 against
yt-dlp 2026.08.19. **Tests must never hit the network** — they read these files instead.

| File | Source | Why it exists |
|---|---|---|
| `youtube_multi_audio.json` | `youtube.com/watch?v=0e3GPea1Tyg` | 24 audio languages; `en-US` is the original (`language_preference=10`), the rest are dubs (`-1`). Mixed HTTPS + HLS/DASH formats. |
| `youtube_many_subs.json` | `youtube.com/watch?v=iG9CE55wbtY` | 64 manual subtitle languages, an `en-orig` ASR track, and machine translations sourced from both manual and ASR tracks. |
| `youtube_playlist_flat.json` | `youtube.com/@TED/videos` | `extract_flat` playlist: entries are `_type: url` stubs with no formats. |
| `other_site.json` | `archive.org/details/BigBuckBunny_124` | Non-YouTube. Formats have `vcodec`/`acodec` of `None` (unknown, not `"none"`). |

Two size reductions were applied by `scripts/capture_fixtures.py` and are recorded in the files:
- Format `url` is blanked and `fragments`/`http_headers` dropped — normalisation never reads them.
- Subtitle URLs keep only the `lang`, `tlang`, `kind`, `fmt` and `v` query parameters, because
  those are exactly what distinguishes an auto-generated track from a machine-translated one.

`youtube_many_subs.json` was additionally trimmed (see its `_fixture_note` field): the real
response had **10147** `automatic_captions` keys x 8 formats, which is 16 MiB of JSON.
