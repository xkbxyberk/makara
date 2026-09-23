# VideoDownloader — Specification

A local-only media workstation over yt-dlp and FFmpeg. One user, one Mac, never deployed.
Four areas share one job queue: **Inspect · Download · Library · Studio**.

Turkish is the only UI language shipped; every string lives in `frontend/src/i18n/tr.ts`.

---

## 1. Product decisions

| Decision | Choice |
|---|---|
| Shell | pywebview desktop window + double-clickable `VideoDownloader.command`; also reachable in a browser at `http://127.0.0.1:8787` |
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
  main.py            FastAPI on 127.0.0.1:8787, serves frontend/dist as an SPA
  paths.py           every filesystem root; VD_DATA_DIR / VD_DOWNLOAD_DIR override for tests
  errors.py          raw failure -> stable code (never Turkish prose)
  doctor.py          yt-dlp / JS runtime / ffmpeg capability probing
  ytdlp/params.py    shared YoutubeDL params + JS-runtime discovery
  ytdlp/normalize.py raw info dict -> the one model every screen consumes
  ytdlp/command.py   equivalent yt-dlp command line, for display only
  workers/           one child process per extraction or job
  inspect_service.py drives the worker; serves fixtures when VD_FIXTURE_MODE=1
  api/routes.py      the HTTP surface
frontend/src/
  i18n/tr.ts         every user-facing string
  theme.css          design tokens, light + dark
  lib/api.ts         typed client; ApiError carries a code, not a sentence
  lib/format.ts      bytes, duration, bitrate, dates, language names
  components/ui.tsx  Panel, Term (tooltip), Badge, Empty/Loading/Error states, CopyButton
  routes/            InspectRoute, DoctorRoute
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
| `POST` | `/api/inspect` | `{url, flat?}` → the normalised model, or `{error: {code, raw}}` |
| `POST` | `/api/command` | selection → the equivalent `yt-dlp` argv, for display |
| `POST` | `/api/plan` | selection → filename preview, size, compatibility notices, copy/transcode plan, command |
| `GET` | `/api/jobs` | the queue |
| `POST` | `/api/jobs` | selection → a queued job (400 `SELECTION_INVALID`, 410 `INSPECT_EXPIRED`) |
| `POST` | `/api/jobs/{id}/cancel` · `/retry` | kill the job's process group · requeue and resume |
| `DELETE` | `/api/jobs/{id}` | remove from the list (never deletes media) |
| `GET` | `/api/events` | SSE: `snapshot` on connect, then `job` / `removed` events |
| `GET`/`PUT` | `/api/settings` | download folder, template, concurrency (1–6), default mode |
| `POST` | `/api/notify` | macOS notification; text comes from the UI, passed as AppleScript argv |
| `POST` | `/api/reveal` | select a file in Finder (only inside the download folder) |

Inspect results carry an `inspect_id` (server-side cache of the last 8) and `defaults` per
mode. All non-GET requests from another origin are rejected, and the Host header must be
`127.0.0.1` or `localhost`.

Errors are `{"error": {"code", "raw", "detail"}}` with HTTP 400 for `INVALID_URL` /
`UNSUPPORTED_SITE` and 502 otherwise. Codes: `INVALID_URL`, `UNSUPPORTED_SITE`,
`LOGIN_REQUIRED`, `AGE_RESTRICTED`, `GEO_RESTRICTED`, `VIDEO_UNAVAILABLE`, `DRM_PROTECTED`,
`LIVE_NOT_STARTED`, `NO_JS_RUNTIME`, `NETWORK`, `TIMEOUT`, `UNKNOWN`.

The doctor returns `{status, checks: [{id, status, values, fix}]}` for `yt_dlp`, `js_runtime`
and `ffmpeg`. The ffmpeg check reports a capability matrix; `subtitles_filter` (libass) and
`webp` (libwebp) are absent on this machine, which is why subtitle burn-in and animated WebP
are not offered.

## 5. Screens

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
- **Loading / error** states as above. **Ready:** one row per dependency with a status dot,
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

### Library, Studio, Settings
Present in the sidebar, disabled, labelled "yakında". Specified in PLAN.md milestones M3–M8.

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

`./scripts/check.sh` is the gate: ruff, ruff-format, mypy, pytest, tsc, eslint, vitest, the
production build, and Playwright. Tests never reach the network; the one live test is behind
`RUN_LIVE_TESTS=1`. Per-feature end-to-end scenarios live in `tests.json`.
