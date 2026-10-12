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

## M3 — Library and Settings ✅ done

- [x] SQLite catalogue of every finished download: source, site, channel, dates, tracks (from
      ffprobe), files, size, thumbnail (a video frame, or an audio file's cover)
- [x] Grid and list views, search, sort, site/kind/missing filters, open in the default player,
      reveal in Finder — by item id, never by arbitrary path
- [x] Missing-file scan (on start-up and on demand): "Eksik" badge; a moved file is re-linked
      when size *and* duration match (download folder by size, then Spotlight by name), never
      to a file another item already owns
- [x] Move to Trash behind a native confirmation dialog whose default is "Vazgeç"
- [x] Settings screen: download folder (native macOS picker), naming template with live
      preview, concurrency, default mode, theme, clipboard watcher (opt-in), notifications
- [x] One-click yt-dlp update in Sistem (upgrades `uv.lock`, so it survives the next launch)
- [x] Opt-in clipboard watcher offering to inspect a copied link

Proof: `./scripts/check.sh` (now also fails if the e2e server logged an exception).

## M4 — Studio core ✅ done

- [x] Source: a library item ("Stüdyo'da aç") or any local file (path or native picker);
      the source is only read, outputs are new files next to it
- [x] Convert and extract audio, including two-pass EBU R128 loudness normalisation
- [x] Lossless (keyframe) cut vs frame-accurate (re-encode) cut, both explained in the UI; the
      keyframe a lossless start will snap to is shown before the run; several segments,
      joined or separate; chapters as quick picks
- [x] Remux and a track editor: keep/drop, reorder, language and default flags, add external
      audio/subtitle files; MP4 restrictions refused with an explanation
- [x] Subtitle tools: VTT/SRT/ASS conversion, time shift, YouTube auto-caption VTT cleanup
      (auto-detected)
- [x] Exact FFmpeg command preview before every run; runs in the shared queue; results join
      the library

Proof: `./scripts/check.sh`; `frontend/e2e/studio.spec.cts` trims a local file losslessly and
checks the duration with ffprobe.

## Native macOS app + Safari extension (N0–N8, before M5)

Berk's decision (2026-10-12): path B — a real `VideoDownloader.app` whose screens move to
SwiftUI one by one, over the same Python backend and HTTP API; a Safari extension that detects
downloadable media and downloads it with **one click using a chosen profile** (never
automatically). Berk is in the Apple Developer Program. App Store distribution is impossible
(guideline 5.2.3) and not wanted; the app is built and signed on this Mac.

Ground rules for the whole track:
- The backend stays the single source of truth: yt-dlp, FFmpeg, naming, library, queue. Swift
  never runs yt-dlp or FFmpeg itself and never builds an output path.
- The app is usable at every step: screens not yet ported are shown by the existing web UI in an
  embedded web view (`?embedded=1` hides its own sidebar/toolbar), so the migration never
  breaks a working feature.
- Swift code lives in a local Swift package (`macos/VideoDownloaderKit`: API client, models, view
  models, views) so `swift test` runs from the command line; the Xcode project only holds the
  app and the extension targets. No new system-wide tools (no XcodeGen/Tuist): the project
  skeleton comes from Apple's own `safari-web-extension-packager`.
- Contract tests: pytest writes sample API responses to `tests/fixtures/api/*.json`; Swift
  tests decode every one of them. A backend change that breaks the app fails the gate.
- UI tests: XCUITest drives the app against the backend in fixture mode (port 8788), with
  light/dark/narrow screenshots like the web suite. `scripts/check.sh` gains `swift test` and
  `xcodebuild test`.
- Strings: the SwiftUI screens get their Turkish text from one String Catalog
  (`Localizable.xcstrings`), the native counterpart of `tr.ts`; error codes are rendered there.

### N0 — Spike: prove the risky parts first
- [ ] Xcode project skeleton (app + Safari web extension) generated with Apple's packager,
      signed with Berk's team, building from `xcodebuild` without opening Xcode
- [ ] A development-signed extension stays enabled after Safari is quit and reopened, without
      "Allow unsigned extensions"
- [ ] Extension → `sendNativeMessage` → sandboxed handler → `127.0.0.1:8787` round trip works
      (`com.apple.security.network.client` only, no temporary exceptions)
- [ ] XCUITest can launch and drive the app from the command line
Stop and report if any of these fails; the plan changes with it.

### N1 — Profiles and one-click download (backend)
- [ ] Profiles: built-in ones plus Berk's own, each = output mode + quality cap + codec
      preference + audio format + audio language rule + subtitle rule (pulls the profile half
      of M7 forward; cookies stay in M7)
- [ ] `POST /api/quick` `{url, profile}`: inspect, apply the profile to the default selection,
      queue the job; reports what it chose and any compatibility warning
- [ ] `GET /api/supports?url=`: offline check against yt-dlp's extractors (no network), so the
      extension can light up its icon instantly; the generic extractor alone does not count
- [ ] Profiles are editable in the web UI's Settings and selectable in the download panel

### N2 — App shell in SwiftUI
- [ ] `NavigationSplitView` window with the sidebar and toolbar of today's design, a real
      Settings window (⌘,), menu commands and keyboard shortcuts
- [ ] Starts the backend as a child process (from this project checkout), waits for health,
      stops it on quit; shows a clear state when the backend cannot start
- [ ] SSE event client; system notifications via UserNotifications; `videodownloader://` URL
      scheme; a URL dropped on the Dock icon or window is inspected
- [ ] Every screen still reachable (embedded web view); `pywebview` launcher retired

### N3 — Safari extension
- [ ] Toolbar icon lights up on pages yt-dlp supports, and on pages with a `<video>`/`<audio>`
      or a streaming manifest; nothing is sent anywhere until Berk clicks
- [ ] Popup: title, duration, best quality and size estimate from the inspect, a profile
      picker (video and audio profiles, last choice remembered per site), one "İndir" button,
      "Uygulamada incele" for the full track picker; DRM pages say so and offer nothing
- [ ] Right-click a link → "VideoDownloader ile indir" with a profile submenu; keyboard shortcut
- [ ] Job progress visible in the popup; the app's queue shows the same job

### N4 — İndirmeler (queue) and Sistem (doctor) in SwiftUI
### N5 — İncele + download panel + track picker in SwiftUI
### N6 — Kütüphane in SwiftUI (grid/list, inspector, Quick Look, Trash with confirmation)
### N7 — Stüdyo and Ayarlar in SwiftUI
Each: feature parity with the web screen (same backend calls, same states: empty, loading,
error), its XCUITest scenarios and screenshots, then the embedded web view for it is removed.

### N8 — Wrap-up
- [ ] Decide with Berk whether the web UI stays reachable in a browser or is removed
- [ ] App installed in `~/Applications`, signed with Developer ID; docs and CLAUDE.md updated

## M5 — Sections and SponsorBlock · M6 — Playlists and channels
## M7 — Browser cookies (profiles moved to N1) · M8 — Transcode and target size

Then P2: subscriptions, live recording, local Whisper transcription (ask before any model
download). Burn-in stays impossible until an FFmpeg build with libass is installed.
