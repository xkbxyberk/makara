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
downloadable media and downloads it with **one click from the choices that video actually
offers** (never automatically; no fixed profiles). Berk is in the Apple Developer Program. App Store distribution is impossible
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

### N0 — Spike: prove the risky parts first ✅ done
- [x] Xcode project skeleton (app + Safari web extension) generated with Apple's packager,
      signed with Berk's team, building from `xcodebuild` without opening Xcode
- [x] A development-signed extension stays enabled after Safari is quit and reopened, without
      "Allow unsigned extensions"
- [x] Extension → `sendNativeMessage` → sandboxed handler → `127.0.0.1:8787` round trip works
      (`com.apple.security.network.client` only, no temporary exceptions)
- [x] XCUITest can launch and drive the app from the command line
Stop and report if any of these fails; the plan changes with it.

### N1 — Quick choices from the source (backend) ✅ done
No fixed profiles: the choices come from the inspected video itself.
- [x] The inspect model gains `offers`: one video choice per distinct resolution/fps/HDR the
      source has, each resolved for both outputs (MKV: best variant, no re-encode; MP4: a
      compatible variant, or the re-encode it needs, said up front), plus the audio-only
      choices (each native audio stream as-is, and conversion to M4A/MP3), each with its
      size estimate (exact vs estimated, as everywhere) and a ready-to-queue selection.
      Built on `selection.py`, so the download panel and the extension can never disagree
- [x] Language and subtitle defaults stay as today (original audio, manual TR/EN), changeable
      from the languages that video really has
- [x] A "last choice" rule (e.g. 1080p · MKV · original audio) maps to the closest offer of any
      other video, so the remembered choice is pre-selected and one click still suffices
- [x] `GET /api/supports?url=`: offline check against yt-dlp's extractors (no network), so the
      extension can light up its icon instantly; the generic extractor alone does not count
- [x] The web download panel shows the same quick choices above the full track picker

### N2 — App shell in SwiftUI ✅ done
- [x] `NavigationSplitView` window with the sidebar and toolbar of today's design, a real
      Settings window (⌘,), menu commands and keyboard shortcuts
- [x] Starts the backend as a child process (from this project checkout), waits for health,
      stops it on quit; shows a clear state when the backend cannot start
- [x] SSE event client; system notifications via UserNotifications; `videodownloader://` URL
      scheme; a URL dropped on the Dock icon or window is inspected
- [x] Every screen still reachable (embedded web view); `pywebview` launcher retired

### N3 — Safari extension ✅ done (live-checked by Berk, 13 Oct)
- [x] Toolbar icon lights up on pages yt-dlp supports, and on pages with a `<video>`/`<audio>`
      or a streaming manifest; nothing is sent anywhere until Berk clicks
- [x] Popup: opening it inspects the page (the server cache makes a re-open instant); title,
      duration, then the video's own choices from N1 (MKV/MP4 switch, one row per quality with
      codec and size, audio-only rows, languages/subtitles from that video); the last choice
      for that site is pre-selected; "Uygulamada incele" opens the full track picker; DRM
      pages say so and offer nothing
- [x] Right-click a link → "VideoDownloader ile indir" (uses the remembered choice) or
      "VideoDownloader’da incele" (the full choices, in the app: Safari cannot open the popup
      for another page); keyboard shortcut ⌃⇧D opens the popup
- [x] Job progress visible in the popup; the app's queue shows the same job

### N4 — İndirmeler (queue) and Sistem (doctor) in SwiftUI ✅ done
- [x] İndirmeler: the live list from the app's own event stream (newest first), loading /
      empty / reconnecting states, per-job progress (determinate or not, as the web rules),
      stage, %, item i/n, speed, ETA, mode and "Safari oturumuyla" badges, errors with their
      raw details, output files with "Finder’da göster", warnings; cancel / retry / remove
      buttons and the same in a context menu (plus "Bağlantıyı kopyala")
- [x] Sistem: a grouped form per check (values, runtimes, FFmpeg capabilities, missing
      features explained, the copyable fix command), yt-dlp update, the Safari session state
      with its Full Disk Access / Settings shortcut, refresh in the toolbar, loading and error
- [x] Error and state wording copied into the native catalog; a vitest keeps it equal to `tr.ts`
- [x] Both screens no longer use the embedded web page in the app (the browser UI keeps them)
### N5 — İncele + download panel + track picker in SwiftUI ✅ done
- [x] İncele: link field, ⌘V anywhere, drops, links from Safari / the Dock / the URL scheme and
      the clipboard banner (now native, on every screen); empty / loading / error states; the
      video (metadata, warnings, video and muxed tables, audio groups, three subtitle groups,
      chapters, heatmap, thumbnails, commands) and the playlist view
- [x] Download panel: outputs, the video's quick choices (remembered per site, saved only when
      clicked), summary, size and file name from `/api/plan`, its notices, İndir (⌘↵) only on
      the plan of exactly this selection, "Kuyruğa eklendi" → İndirmeler, INSPECT_EXPIRED
- [x] Track picker: video, audio languages and variants, audio-only format and quality,
      subtitles (machine translations filtered), extras, file name template, the command
- [x] Tests never load a remote image: the app shows none against a fixture-mode backend, and
      the e2e browser's requests outside this Mac go to a closed port
### N6 — Kütüphane in SwiftUI (grid/list, inspector, Quick Look, Trash with confirmation) ✅ done
- [x] Grid and list (`Table`), search in the toolbar, site / kind / sort / missing filters, the
      count and size under the title, live refresh on the server's `library` event
- [x] The window's inspector: thumbnail, badges, tracks (languages from the file), files,
      source, added; Oynat (also a double-click), Göz At (Quick Look, also the space bar),
      Finder'da göster, Stüdyo'da aç (handed to the embedded Stüdyo page), Çöp Kutusu'na taşı
      after a confirmation; the same in a context menu
- [x] "Dosyaları denetle" and its result; the catalogue-failed banner is native, on every screen
### N7 — Stüdyo (redesigned) and Ayarlar in SwiftUI ✅ done
- [x] Berk's request: Kütüphane removes the records of missing items (one, or all at once)
- [x] Stüdyo redesigned around the cut (Berk's request): macOS's own player, stepped frame by
      frame; a Photos-style filmstrip with two yellow handles snapped to the source's frames
      (to its keyframes for a lossless cut); start/end as time and frame, a frame either way,
      I/O from the playhead, keyboard; several pieces, chapters, joining. The backend cuts on
      exactly the chosen frames (`start_frame`/`end_frame`; tested frame by frame)
- [x] Preview copies for what AVFoundation cannot step through (MKV/WebM, VP9/AV1): H.264/HEVC
      copied, the rest VideoToolbox H.264, timestamps passed through, cached in the data folder
- [x] Ses, Remux ve izler, Altyazı as before, in the inspector; the exact plan and its commands
- [x] Ayarlar in the Mac's own Settings window, applied at once (a refused switch springs back)
- [x] No web page is left in the app (WebBridge removed)

Each of N4–N7: feature parity with the web screen (same backend calls, same states: empty, loading,
error), its XCUITest scenarios and screenshots, then the embedded web view for it is removed.

### N8 — Wrap-up
- [x] Decided 2026-10-14: the web UI is removed (the native app is the only UI)
- [x] Removed `frontend/`, the SPA serving and the web-only endpoints (`/command`, `/notify`, the
  AppleScript folder/file pickers); the extension's tests moved to `macos/extension-tests/`
- [ ] App installed in `~/Applications`, signed with Developer ID -- *after* P-series below

## P-series — Berk's wishes of 2026-10-14 (before signing and installing)
Working mode from now on: development first; no full gate / UI tests / review agents unless
Berk asks (session limits).

### P1 — Safari extension beyond YouTube
- [x] Every site yt-dlp supports, not only YouTube: the content script finds the media Berk is
      watching (a playing `<video>`/`<audio>`, MSE/blob players included) and its *permalink*
      (X: the tweet's `/status/` link inside the `<article>`; generic: canonical/og:url, the
      page itself), asks `/api/supports` (offline), and only then offers it
- [x] Both, chosen in Settings (Berk, 2026-10-14): by default a small dismissible in-page offer
      ("Bu videoyu indir?" with the quick choice and "İncele"), once per media, mutable per
      site; or the toolbar icon only. The toolbar popup works either way
- [x] Site-specific permalink finders kept in one table (X, Instagram, TikTok, Reddit,
      Vimeo, Facebook…), generic fallback for the rest
- [ ] Berk's live check in Safari (restart Safari after the rebuild): X timeline, a YouTube
      video, one more site; the card, "Bu sitede sorma", and the "icon only" setting

### P2 — Download acceleration (IDM-style)
- [ ] Fragmented formats (HLS/DASH, most sites): yt-dlp's `concurrent_fragment_downloads`
- [ ] Single-file HTTP formats: several connections with byte ranges via **aria2c** (Berk chose
      it 2026-10-14 and so approved `brew install aria2`); per-download connection count,
      live per-segment progress in İndirmeler
- [ ] Pause / resume (keep `.part` files), a global speed limit, a "faster" setting

### P3 — Library by kind in the sidebar
- [ ] Kütüphane splits by what was downloaded (Berk's choice): Videolar · Müzik · Stüdyo, under
      the Kütüphane heading, with counts; the site and other filters stay inside each

### P4 — Menu bar app, launch at login, Dock
- [ ] A status-bar item (default on) with the app's template icon: active downloads with
      progress, "Panodaki bağlantıyı indir/incele", open window, pause all, quit
- [ ] Settings: "Açılışta başlat" (SMAppService), "Dock'ta göster" (activation policy),
      "Menü çubuğunda göster"; closing the window keeps the app (and the extension's server)
      running when it lives in the menu bar
- [ ] Defaults: menu bar on, launch at login on after first run (asked once)

### P5 — Icon and design
- [ ] A professional SVG app icon that says what it does (download arrow + film/waveform),
      rendered to the asset catalog sizes, the extension's toolbar icons and a template
      status-bar glyph; UI/UX polish pass over every screen

### P6 — Ideas added by Claude (to discuss)
- [ ] Extension: "zaten indirildi" when the page's video is in the library; one-click with the
      remembered choice from the in-page offer
- [ ] Notifications with actions (Finder'da göster, Oynat); a Dock/menu-bar progress ring
- [ ] Drop a link on the menu-bar icon; ⌥-click a link in Safari to download it at once
- [ ] Queue: drag to reorder, retry with backoff, "bitince Mac'i uyut"
- [ ] yt-dlp updated automatically (weekly, in the background, when nothing is downloading)
- [ ] Disk-space check before a big download; duplicate detection before downloading again
- [ ] Earlier milestones still open: M5 (chapters/SponsorBlock), M6 (playlists/channels)

## M5 — Sections and SponsorBlock · M6 — Playlists and channels
## M7 — Presets and browser cookies (Safari session for YouTube pulled forward, 2026-10-13) · M8 — Transcode and target size

Then P2: subscriptions, live recording, local Whisper transcription (ask before any model
download). Burn-in stays impossible until an FFmpeg build with libass is installed.
