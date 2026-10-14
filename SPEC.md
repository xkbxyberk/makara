# VideoDownloader — Specification

A local-only media workstation over yt-dlp and FFmpeg. One user, one Mac, never deployed.
Four areas share one job queue: **Inspect · Download · Library · Studio**.

Turkish is the only UI language shipped; every string lives in the app's `Localizable.xcstrings` (the Safari extension has its own `_locales/tr/messages.json`).

---

## 1. Product decisions

| Decision | Choice |
|---|---|
| Shell (until N2) | pywebview desktop window + double-clickable `Makara.command`; also reachable in a browser at `http://127.0.0.1:8787` |
| Shell (from N2, built) | A native `VideoDownloader.app` (SwiftUI) over the same backend: native sidebar, title bar, menus (Git: ⌘1–⌘5), Settings window (⌘,), Dock badge, notifications, `videodownloader://`. It starts the backend itself and stops it on quit. Every screen and the Settings window are native SwiftUI (N4–N7); the app shows no web page. The browser UI was removed in N8 (2026-10-14). The pywebview window is gone |
| Safari | A Safari web extension inside the app: detects downloadable media and downloads with one click from the qualities and audio streams that video actually offers. Never downloads on its own |
| Safari extension (N3) | Toolbar icon: filled on pages yt-dlp supports or that play media, outline otherwise; only the page URL goes to the app on this Mac, offline. Popup: the video's own choices (MKV / MP4 / Sadece ses, size and re-encode per row, audio language, subtitles), the site's last clicked choice preselected, one "İndir", live progress, "Uygulamada incele". When the app is closed it offers to open it. Lists open in the app; DRM and unsupported pages say so. Right-click a link: download with the remembered choice, or inspect in the app. ⌃⇧D opens the popup |
| Quick choices | No fixed profiles. The inspect model lists the source's own video qualities (per output, MKV or MP4) and audio-only options with sizes; the last choice per site is remembered as a rule and pre-selected |
| Distribution | Built and signed on this Mac with Berk's Apple Developer team; never the App Store (guideline 5.2.3) |
| Default output | **Archive MKV** — no re-encoding, all selected tracks language-tagged |
| Folder layout | `~/Movies/VideoDownloader/<site>/<channel>/<YYYY-MM-DD> - <title> [<id>].<ext>` |
| Library vs Finder | Mark, never delete. A missing file gets a badge; a moved file is re-linked when size and duration match |
| Default track selection | Original audio + manual TR/EN subtitles. Dubs and auto-captions are opt-in |
| Visual direction | macOS-native clear: system typography, light grey surfaces, one system-blue accent, full dark mode |
| Player | Always external (IINA/QuickTime). No in-app player is built |
| Deleting | Move to Trash, with confirmation |
| yt-dlp channel | stable, updated from inside the app; nightly available as an escape hatch |

## 2. Architecture

```
backend/app/
  main.py            FastAPI on 127.0.0.1:8787, JSON only (no web page since N8)
  paths.py           every filesystem root; VD_DATA_DIR / VD_DOWNLOAD_DIR override for tests
  errors.py          raw failure -> stable code (never Turkish prose)
  doctor.py          yt-dlp / JS runtime / ffmpeg capability probing
  ytdlp/params.py    shared YoutubeDL params + JS-runtime discovery
  ytdlp/normalize.py raw info dict -> the one model every screen consumes
  ytdlp/command.py   equivalent yt-dlp command line, for display only
  workers/           one child process per extraction or job
  inspect_service.py drives the worker; serves fixtures when VD_FIXTURE_MODE=1
  api/routes.py      the HTTP surface
macos/
  VideoDownloader/     the app target (starts the backend), the Safari extension target, UI tests
  VideoDownloaderKit/  every screen (SwiftUI), APIClient, Localizable.xcstrings
  extension/           the Safari web extension (plain JS)
  extension-tests/     shared.js unit tests (node --test) and the popup e2e (Playwright)
```

**Why a child process per job:** cancelling means killing the child, and a yt-dlp or FFmpeg
crash cannot take the server down. The contract is one JSON request on stdin and one JSON
response on stdout; progress will become JSONL lines on the same pipe in M2.

**Why the backend returns codes, not sentences:** a second language is then one file.

## 3. Data model

### Normalised inspect model (the contract)

```jsonc
{
  "kind": "video",
  "media": { "id", "title", "description", "webpage_url", "extractor", "channel",
             "channel_url", "upload_date", "timestamp", "duration", "view_count",
             "like_count", "live_status", "availability", "age_limit", "language", "thumbnail" },
  "video_formats": [ { "format_id", "ext", "container", "protocol", "is_manifest",
                       "filesize", "filesize_kind", "filesize_unreliable", "tbr", "drm",
                       "format_note", "width", "height", "resolution", "fps", "vcodec",
                       "vcodec_label", "vbr", "dynamic_range", "has_audio", "acodec_label" } ],
  "muxed_formats": [ /* same shape; audio and video in one format */ ],
  "audio_languages": [ { "language", "role", "tracks": [ { /* + acodec, abr, asr, channels,
                          language_preference, role */ } ] } ],
  "subtitles": { "manual": [...], "auto": [...], "auto_translated": [...], "has_live_chat": bool },
  "chapters": [ { "start_time", "end_time", "title" } ],
  "heatmap":  [ { "start_time", "end_time", "value" } ],
  "thumbnails": [ { "id", "url", "width", "height", "preference" } ],
  "warnings": ["DRM_PRESENT" | "DRM_MAYBE" | "NO_AUDIO_LANGUAGE_INFO" | "SIZES_ARE_ESTIMATES" | "LIVE_CONTENT"],
  "source_url": "...",
  "commands": { "inspect": "...", "suggested": "..." }
}
```

A playlist returns `{"kind": "playlist", media, entries[], entry_count, warnings}`.

**`filesize_kind`** is `exact` (yt-dlp `filesize`), `approx` (`filesize_approx`), `estimated`
(`tbr * duration`), or `unknown`. `filesize_unreliable` is true when an estimate comes off a
manifest format, because there `tbr` is often peak rather than average bitrate.

**`role`** is derived only from `language_preference`: `10` original, `5` default, `-10`
descriptive, otherwise `dub`. When a video has exactly one audio language and it would read as
a dub, the role becomes `unknown` instead — with nothing to contrast against, the UI says
nothing rather than something false. **yt-dlp cannot distinguish a human dub from an AI
auto-dub**, so no such badge exists.

**Subtitle classification.** `subtitles` minus `live_chat` is `manual`. Inside
`automatic_captions`: a key ending `-orig`, or a URL carrying `kind=asr`, is `auto`; a URL
carrying `tlang=`, or a name reading "X from Y", is `auto_translated`.

### Job model

`status`: `queued → running → done | failed | cancelled` (failed/cancelled → queued on retry).
`stage` while running: `starting → preparing → downloading → (postprocessing) → (merging |
converting)`; `cancelling` while a cancel is in flight. `progress` is 0..1 *within the stage*;
the download stage is weighted by file size so a finished video reads ~90%, not 33%.

Stored in SQLite (`jobs` table: id, status, stage, title, source_url, mode, request JSON,
progress, speed, eta, item_index/count, output_files JSON, error_code, error_raw, timestamps).
On start-up, jobs left `running` are requeued; each job's scratch directory
`<download dir>/.vd-work/<id>/` persists across retries so yt-dlp resumes `.part` files.

### Download pipeline (one child process per job)

1. **Side pass** (yt-dlp, `skip_download`): subtitles (`subtitleslangs` anchored and escaped),
   thumbnail converted to JPEG, description, info.json.
2. **Stream pass** (yt-dlp): each selected format as its own file (`-f v,a1,a2`). Audio-only mode
   uses `FFmpegExtractAudio` + `FFmpegMetadata` + `EmbedThumbnail` here.
3. **Finalize** (our FFmpeg argv, progress from `-progress pipe:1`):
   - MKV: copy everything; audio languages as ISO 639-2 tags, first audio default, subtitles to
     SRT (ASS kept), chapters from the info dict, cover as a `cover.jpg` attachment.
   - Compatible MP4: probe the real streams; copy H.264/HEVC (tagged `avc1`/`hvc1`) and AAC,
     re-encode anything else (libx264 CRF 20; AudioToolbox AAC when available); `mov_text`
     subtitles; `+faststart`.
   - Separate: `<stem>.<ext>`, `<stem>.<lang>.<ext>` for audio, `<stem>.<key>.srt` (VTT converted)
     for subtitles — the naming IINA and VLC auto-load.
   The final path comes from the filename template, must resolve inside the download folder,
   and gets a " (2)" suffix instead of ever overwriting.

## 4. API surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | liveness + whether fixture mode is on |
| `GET` | `/api/doctor` | dependency report (see below) |
| `POST` | `/api/inspect` | `{url, reuse?, rule?}` → the normalised model with `offers` (quick choices) and `offers.preselected`, or `{error: {code, raw}}`. `reuse` returns an inspection of the same URL from the last 15 minutes |
| `GET` | `/api/supports?url=` | offline: does a yt-dlp extractor (other than the generic one) match this URL → `{supported, extractor, working}` |
| `POST` | `/api/quick` | `{inspect_id, offer_id, output?}` or `{url, rule}`, plus optional `audio_language`, `subtitle_keys` → `{job, offer_id, output, rule, selection}` (400 `OFFER_UNKNOWN`, `QUICK_NEEDS_VIDEO`, `QUICK_NEEDS_SOURCE`, `QUICK_NOTHING_OFFERED`; 410 `INSPECT_EXPIRED`) |
| `POST` | `/api/command` | selection → the equivalent `yt-dlp` argv, for display |
| `POST` | `/api/plan` | selection → filename preview, size, compatibility notices, copy/transcode plan, command |
| `GET` | `/api/jobs` | the queue |
| `POST` | `/api/jobs` | selection → a queued job (400 `SELECTION_INVALID`, 410 `INSPECT_EXPIRED`) |
| `POST` | `/api/jobs/{id}/cancel` · `/retry` | kill the job's process group · requeue and resume |
| `DELETE` | `/api/jobs/{id}` | remove from the list (never deletes media) |
| `GET` | `/api/events` | SSE: `snapshot` on connect, then `job` / `removed` events |
| `GET`/`PUT` | `/api/settings` | download folder, template, concurrency (1–6), default mode |
| `POST` | `/api/notify` | macOS notification; text comes from the UI, passed as AppleScript argv |
| `POST` | `/api/jobs/{id}/reveal` | `{index}` → select that job's output file in Finder (checked against that job's own folder) |
| `GET` | `/api/library` | items + facets; `search`, `site`, `kind`, `status`, `sort` |
| `POST` | `/api/library/scan` | re-check files on disk; returns checked/missing/repaired/restored |
| `GET` | `/api/library/{id}/thumbnail` | the item's JPEG (only from the app's thumbnail folder) |
| `POST` | `/api/library/{id}/open` · `/reveal` · `/trash` | default player · Finder · macOS Trash |
| `POST` | `/api/settings/preview-template` | template + sample values → rendered path |
| `POST` | `/api/system/pick-folder` | native folder picker (prompt text from the UI, passed as argv) |
| `POST` | `/api/system/update-ytdlp` | `uv lock --upgrade-package yt-dlp …` + `uv sync` (409 while jobs run) |
| `POST` | `/api/studio/probe` | `{path}` or `{item_id}` → streams, duration, chapters |
| `POST` | `/api/studio/plan` | operation → exact commands, notices, output paths |
| `POST` | `/api/studio/jobs` | operation → a queued studio job |
| `POST` | `/api/system/pick-file` | native file picker |

Inspect results carry an `inspect_id` (server-side cache of the last 8) and `defaults` per
mode. All non-GET requests from another origin are rejected, and the Host header must be
`127.0.0.1` or `localhost`.

Errors are `{"error": {"code", "raw", "detail"}}` with HTTP 400 for `INVALID_URL` /
`UNSUPPORTED_SITE` and 502 otherwise. Codes: `INVALID_URL`, `UNSUPPORTED_SITE`,
`LOGIN_REQUIRED`, `AGE_RESTRICTED`, `GEO_RESTRICTED`, `VIDEO_UNAVAILABLE`, `DRM_PROTECTED`,
`LIVE_NOT_STARTED`, `NO_JS_RUNTIME`, `NETWORK`, `TIMEOUT`, `UNKNOWN`.

The doctor returns `{status, checks: [{id, status, values, fix}]}` for `yt_dlp`, `js_runtime`
and `ffmpeg`. The ffmpeg check reports a capability matrix; `subtitles_filter` (libass) and
`webp` (libwebp) are present only with Homebrew's `ffmpeg-full`, which this Mac now uses.

### Quick choices (`offers`, N1)
`offers.video` has one row per distinct height / frame rate / dynamic range the source has,
largest first. Each row carries, for `mkv` and `compat_mp4` separately: the chosen variant
(archive: the efficient codec, never re-encoded; MP4: a compatible variant, else the one that
will be re-encoded, `video_step` says which), its size estimate (video + original audio, with
the usual exact/estimated confidence) and a ready-to-queue `selection`. A row made only of
YouTube's AI upscales says so (`ai_upscaled`) and is never matched by a rule when a real size
exists. `outputs[o].recommended` marks today's two-click default in that output, and each
output's `step` is the heaviest thing that happens to any track (copy < probe < transcode). `offers.audio` lists the source's own
streams that copy into Opus or M4A (`step: copy`), then conversions to M4A/MP3 (`transcode`,
or `probe` when the source codec is unknown); a conversion starts from the same track as the
audio-only default and its size is never guessed. A *rule* (`{kind: video, height, fps, hdr,
output}` or `{kind: audio, format}`) maps to the same size if present, else the nearest
smaller real size, else the smallest larger one. The web panel remembers the last rule per
site in browser storage, and only when a quick choice was actually clicked. An asked-for audio
language the video lacks is refused (`AUDIO_LANGUAGE_UNKNOWN`), never swapped for the original.
`/api/supports` also answers `kind`: `video`, `playlist` (a channel or user page: open it in
the app) or `unknown`.

## 5. Screens

### Window shell (HIG redesign, after M4)
Follows the macOS Human Interface Guidelines as far as a web view allows. A source-list sidebar
(Medya: İncele, İndirmeler, Kütüphane, Stüdyo · Uygulama: Sistem, Ayarlar) with accent-tinted
symbols and a badge for active jobs; a unified toolbar holding the sidebar toggle, the screen
title and that screen's own actions (Library: search field, grid/list switch, scan; Sistem:
re-check). The theme picker at the foot of the sidebar is three symbols (sun, moon, half circle
for "system"). Colors are macOS semantic colors for light and dark, the accent follows the
system accent where WebKit exposes it, and controls look like their AppKit counterparts
(bordered, prominent, borderless symbol buttons, popup buttons, segmented controls, grouped
sections). In the desktop window the sidebar shows the real vibrancy material behind a
transparent web view (`?shell=native`, only while the theme follows the system). Icons are
Lucide glyphs mapped to SF Symbol names in `components/Icon.tsx`; SF Symbols themselves cannot
be used outside Apple's native frameworks. Below 720 px the sidebar collapses and floats.
Motion is short and only marks change: segmented selections slide, screens fade in, the sidebar
slides, sheets drop from the top, the Library inspector slides in, theme changes cross-fade.
"Reduce motion" turns all of it off. Help tags float above the window and never get clipped.

### Inspect (M1, built)
- **Empty:** a panel explaining that pasting a link lists every quality, language and subtitle,
  and that nothing is downloaded. Hint that ⌘V anywhere starts an inspect.
- **Loading:** spinner, "Çözümleniyor", and a sentence saying yt-dlp is contacting the site.
- **Error:** the coded error rendered in Turkish with a suggested action, plus a
  "Ayrıntıları göster" disclosure holding the raw log, plus retry.
- **Ready:** warning banners → metadata (thumbnail, title, channel, date, duration, views,
  expandable description) → video qualities table → muxed formats table (only if any) →
  audio tracks grouped by language, first group open, role badge per group → subtitles in three
  labelled groups with machine translations collapsed behind a count → chapters → heatmap →
  thumbnails → the equivalent yt-dlp commands with copy buttons.
- Input accepts typing, paste, drag-and-drop, and a global ⌘V.
- A playlist renders a read-only entry list, with a banner explaining why track data is absent
  and a per-row "inspect this video" action.

### Doctor / Sistem (M0, built)
- **Loading / error** states as above. **Ready:** one row per dependency with a status symbol (check, triangle, octagon),
  its values, the ffmpeg capability matrix, a plain-Turkish explanation for each missing
  optional capability, and a copyable fix command when the check is not green.

### Download panel (inside Inspect, M2, built)
- Segmented mode control (Arşiv MKV · Uyumlu MP4 · Ayrı dosyalar · Sadece ses), a one-line
  explanation of the chosen mode, a chip summary of what will be downloaded, the estimated size
  (with its confidence), the full destination path, and compatibility notices.
- **İndir** (or ⌘↵) queues it. "Parçaları seç" opens the track picker: video (radio), audio per
  language (checkbox + variant select; radio in audio mode), subtitles by kind with machine
  translations collapsed behind a search box, extras, audio format and quality, the filename
  template, and the equivalent yt-dlp command.
- **Error:** an expired inspection offers "Yeniden incele"; blocking notices disable İndir.

### İndirmeler (queue, M2, built)
- **Loading** until the SSE snapshot arrives; **empty** state pointing to İncele; a banner while
  the event stream reconnects. Each job: title, mode, status, stage, progress bar (indeterminate
  when the stage has no measurable progress), percent, i/n, speed, ETA; the output files with
  "Finder'da göster"; the coded error with its raw log; cancel / retry / remove.
- The sidebar shows the number of active jobs.

### Kütüphane (M3, built)
- Toolbar: search (title/channel), site, kind and "only missing" filters, sort, grid/list toggle;
  a summary line (count · total size · missing) and "Dosyaları denetle".
- **Grid:** thumbnail, title, channel · duration · size, mode badge, "Eksik" badge. Opening a card
  shows tracks (from ffprobe), files, source and date, with Oynat / Finder'da göster / Çöp
  Kutusu'na taşı. **List:** the same data as a table; the Trash action appears only for an opened
  row.
- **Loading / error / empty** ("Kütüphane boş") and **no-match** ("Eşleşen öğe yok") states.
- Trash asks first in a native `<dialog>` whose initial focus is "Vazgeç"; files go to the macOS
  Trash (in fixture mode to `<data dir>/simulated-trash`) and the record is kept as trashed.
- A missing item's actions are disabled; the scan re-links it when the file turns up.

### Ayarlar (M3, built)
- Download folder (text + native "Seç…" picker; `/` and system folders refused), filename
  template with a live preview rendered from sample values the app supplies, concurrency (1–6),
  default mode, theme (system/light/dark, stored locally), clipboard watcher (opt-in, default
  off), notifications. Save is disabled until something changes; unsaved changes are flagged.

### Clipboard banner (M3, built)
When the opt-in watcher sees a link copied, a banner offers "İncele" / "Yoksay".

### Stüdyo (M4, built)
- **Source panel:** pick a library item, type a path, or "Dosya seç…" (native picker). Probing
  shows name · duration · stream counts · size. **Empty** state explains that the source is
  never modified; **loading** while probing; **error** for a missing or non-media file.
- **Operation panel** (segmented; subtitle files only get "Altyazı", media files the rest):
  - *Ses*: track (if several), format, bitrate, sample rate, channels, "Ses seviyesini eşitle"
    (two-pass EBU R128 to -16 LUFS). Cover art is kept for MP3/M4A/FLAC.
  - *Kes*: Kayıpsız / Kare hassas with tooltips (and "anahtar kare"); segments as start → end
    in seconds or m:ss(.ms), invalid entries outlined; add/remove segments; join when there
    are several; the source's chapters as quick picks.
  - *Remux ve izler*: container MKV/MP4/MOV; a track table (keep, kind, codec, language, title,
    default, move up/down); add external audio/subtitle files.
  - *Altyazı*: convert, shift (seconds, negative = earlier), or clean YouTube auto captions
    (pre-selected when the file looks like one).
  - Output name, defaulting to "<source> (kesit|ses|remux|altyazı)" from the app's catalog.
- **Command panel:** notices (e.g. "Başlangıç 1.5 sn yerine 1 sn olacak"), the exact output
  path(s), every FFmpeg command with a copy button, and the in-app steps described in words.
  "Çalıştır" is disabled until the plan matches the current form and nothing blocks.

**Studio pipeline:** the worker re-probes the source, builds the same plan, runs each step in the
job's scratch folder (`<output folder>/.vd-work/<id>`, same volume), claims the final names
atomically and renames the results in, then removes the scratch folder (and `.vd-work` if empty).
Loudness: pass 1 `loudnorm=print_format=json` measures; pass 2 applies the measured values with
`linear=true`. Lossless trim: `-ss S -to E -i src -map 0 -c copy`; joins via the concat demuxer.
Frame-accurate: libx264 CRF 18 + AAC; joins via `trim`/`atrim` + `concat` (first video and
audio track only). Shift/clean run on parsed cues in Python and write SRT.

## 6. Feature → tool mapping

| Feature | Mechanism |
|---|---|
| Inspect | `YoutubeDL(inspect_params()).extract_info(url, download=False)` + `sanitize_info` |
| Playlist listing | same with `extract_flat="in_playlist"` |
| JS challenge solving | `js_runtimes={"deno": {"path": ...}}`, `yt-dlp-ejs` from `yt-dlp[default]` |
| Multi-audio MKV (M2) | yt-dlp `-f v,a1,a2` (separate files) + our FFmpeg mux with per-stream language and disposition |
| Compatible MP4 (M2) | same, probing the real codecs: copy H.264/HEVC/AAC, re-encode the rest, `mov_text` subtitles |
| Audio extraction (M2) | `FFmpegExtractAudio` + `EmbedThumbnail` + `FFmpegMetadata` |
| SponsorBlock (M5) | `{"key": "SponsorBlock", "categories": …, "when": "after_filter"}` plus `ModifyChapters` for removal |
| Sections (M5) | `download_ranges=download_range_func(...)`, `force_keyframes_at_cuts` |
| Studio (M4) | `ffmpeg` with an argv list and `-progress pipe:1`; never a shell string |

## 7. Out of scope

DRM circumvention of any kind. Any network listener other than 127.0.0.1. Telemetry. Multi-user
support, accounts, sharing. A plugin system. Burning subtitles into the picture and animated
WebP output, because this FFmpeg build lacks libass and libwebp.

## 8. Verification

`./scripts/check.sh` is the gate: ruff, ruff-format, mypy, pytest, the extension's tests
(node --test, Playwright for the popup), Swift package tests, the app build and its UI tests. Tests never reach the network; the one live test is behind
`RUN_LIVE_TESTS=1`. Per-feature end-to-end scenarios live in `tests.json`.
