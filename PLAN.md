# Milestones

Each milestone is one focused session. Acceptance criteria are mirrored in `tests.json`.
The proof for every milestone is the same command: `./scripts/check.sh` exiting 0.

## M0 — Scaffold, dependency doctor, check.sh ✅ done

- [x] uv project, FastAPI on 127.0.0.1, React + TS + Vite, git repo
- [x] `GET /api/doctor` reports yt-dlp version/channel, JS runtimes, ffmpeg capability matrix
- [x] Doctor screen renders every check with a copyable fix; libass/libwebp absence explained
- [x] macOS-native theme with real dark mode; all strings in `frontend/src/i18n/tr.ts`
- [x] `scripts/check.sh` runs lint, types, pytest, vitest, build and Playwright
- [x] `VideoDownloader.command` opens a pywebview window, falling back to the browser

Proof: `./scripts/check.sh` · `open VideoDownloader.command`

## M1 — Inspect ✅ done

- [x] Four real info dicts recorded into `tests/fixtures/infojson/` (multi-audio, many-subtitle,
      playlist, non-YouTube); tests read them and never touch the network
- [x] `normalize.py` + 14 unit tests covering roles, the three subtitle kinds, size tiers,
      `live_chat` filtering, unknown codecs, playlists
- [x] `POST /api/inspect` runs `extract_info` in a child process, returns codes on failure
- [x] Inspect screen: URL input (type / paste / drop / global ⌘V), metadata, video table,
      audio grouped by language with role badges, subtitles in three groups with machine
      translations collapsed, chapters, heatmap, thumbnails, copyable yt-dlp commands
- [x] Empty, loading and error states; Turkish tooltip on every technical term
- [x] Playwright covers all of the above plus screenshots in light, dark and at 420px

Proof: `./scripts/check.sh` · screenshots in `test-results/screenshots/`

## M2 — Download engine, queue, track picker ✅ done

- [x] Track picker: 1 video + N audio + M subtitles + thumbnail + description + info.json
- [x] Output modes: archive MKV · maximum-compatibility MP4 · separate files · audio only, with
      any re-encode stated before the job starts
- [x] Compatibility advisor warns in plain Turkish (VP9/Opus in MP4, AV1 hardware, HDR, …) and
      points at an already-compatible alternative when one exists
- [x] Queue: concurrency limit, stage/percent/speed/ETA over SSE, cancel, retry, resume of
      partial downloads, survives a server restart
- [x] Naming template with a live filename preview; never writes outside the download folder,
      never overwrites an existing file
- [x] Audio-only download to MP3/M4A/Opus/FLAC/WAV with cover art and metadata
- [x] macOS notifications on finish and failure (when the window is in the background)
- [x] "Two clicks": paste → Download gives original audio + manual TR/EN subtitles

Proof: `./scripts/check.sh`. The e2e suite downloads generated test media through the real
yt-dlp + FFmpeg pipeline and checks every output with `ffprobe`; `tests/test_jobs_api.py`
proves a cancelled download *resumes* (the retry sends an HTTP Range request).

## M3 — Library and Settings

- [ ] Settings screen (download folder, naming template, concurrency, default mode, theme);
      the API (`GET/PUT /api/settings`) already exists since M2
- [ ] SQLite catalogue of every finished job (source, site, uploader, tracks, paths, size, preset)
- [ ] Grid and list views, search, sort, filters, reveal in Finder, open in external player
- [ ] Missing-file scan with a badge, path repair on size+duration match
- [ ] Move to Trash behind a confirmation

## M4 — Studio core

- [ ] Convert and extract audio, including EBU R128 loudness normalisation
- [ ] Lossless (keyframe) cut vs frame-accurate (re-encode) cut, both explained in the UI
- [ ] Remux and a track editor: add/remove/reorder, set language and default flags
- [ ] Subtitle tools: VTT/SRT/ASS conversion, time shift, YouTube auto-caption VTT cleanup
- [ ] Exact FFmpeg command preview before every run

## M5 — Sections and SponsorBlock · M6 — Playlists and channels
## M7 — Presets and browser cookies · M8 — Transcode and target size

Then P2: subscriptions, live recording, local Whisper transcription (ask before any model
download). Burn-in stays impossible until an FFmpeg build with libass is installed.
