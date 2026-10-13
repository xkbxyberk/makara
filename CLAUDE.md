# VideoDownloader — notes for a future session

Local-only media workstation on yt-dlp + FFmpeg. macOS arm64, single user (Berk).
**Talk to Berk in Turkish. Code, comments, commits and docs in English.**
**Every user-facing web string lives in `frontend/src/i18n/tr.ts`; native ones in the Kit's `Localizable.xcstrings` (gotcha 37).**

## Commands

| What | Command |
|---|---|
| The gate (lint, types, pytest, vitest, build, e2e) | `./scripts/check.sh` |
| Backend tests only | `uv run pytest -q` |
| Frontend unit tests | `cd frontend && npx vitest run` |
| End-to-end + screenshots | `cd frontend && npx playwright test` |
| Dev servers | `PYTHONPATH=backend uv run python -m app.main` + `cd frontend && npm run dev` |
| Desktop app (builds if needed) | `open VideoDownloader.command` |
| Update yt-dlp | `uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync` (see gotcha 2) |
| macOS app (build / UI tests) | `xcodebuild -project macos/VideoDownloader/VideoDownloader.xcodeproj -scheme VideoDownloader -derivedDataPath macos/build -allowProvisioningUpdates build` (or `test`) |
| Swift package tests | `cd macos/VideoDownloaderKit && swift test` |
| API contract samples (after an API change) | `VD_WRITE_API_SAMPLES=1 uv run pytest -q tests/test_api_samples.py` |
| Re-record fixtures (network!) | `uv run python scripts/capture_fixtures.py [name ...]` |

## Architecture decisions

- **FastAPI on 127.0.0.1:8787**, serving `frontend/dist` as an SPA. Never bind anything else.
- **Every yt-dlp/FFmpeg job runs in its own child process.** Cancel means kill the child; a
  crash cannot take the server down. Worker protocol: one JSON request on stdin, one JSON
  response (later: JSONL progress) on stdout. `shell=True` appears nowhere.
- **`backend/app/ytdlp/normalize.py` is the heart.** Every screen consumes its output and
  every test asserts against it. Change it deliberately.
- **Backend never returns Turkish.** `errors.py` produces stable codes; `tr.ts` renders them.
- **Tests never touch the network.** They read `tests/fixtures/infojson/*.json`, recorded once
  from the real sites. The e2e suite runs the real server with `VD_FIXTURE_MODE=1`.
- Frontend is plain React + hand-written CSS variables. No UI framework, no router, no state
  library — the app is too small to earn them.

## Gotchas that will bite you

1. **JS runtime.** Modern YouTube needs `yt-dlp-ejs` (ships with `yt-dlp[default]`) *and* a
   JavaScript engine. The `YoutubeDL` key is the top-level **`js_runtimes`**, and passing a
   dict *replaces* the deno-only default. Without a runtime yt-dlp does **not** fail — it
   silently drops the `web` client and some formats vanish. Deno 2.9.7 is installed here.
2. **Updating yt-dlp means updating `uv.lock`.** `yt-dlp -U` refuses pip/uv installs
   (`detect_variant()` is `"unknown"`), and `uv pip install -U` is silently reverted because
   `uv run` syncs the venv to the lock on every launch. Use
   `uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync` (the Doctor's
   button does exactly this). Nightly is not a separate PyPI package; it is a `.devN`
   pre-release of `yt-dlp` itself. Report versions from `importlib.metadata`, not the imported
   module, which is stale in the server after an update.
3. **YouTube splits subtitles three ways, not two.** `subtitles` = human. `automatic_captions`
   mixes the ASR track for the spoken language (key has an `-orig` twin, or URL has `kind=asr`)
   with hundreds of machine translations (URL has `tlang=`, or the name reads "X from Y").
   `live_chat` is a fake language key inside `subtitles` — always filter it out.
4. **yt-dlp cannot tell a human dub from an AI auto-dub.** There is no field. The only signal
   is `language_preference` (10 original, 5 default, -10 audio description, else dub). Do not
   invent an "auto-dub" badge; the UI says "Dublaj" and the tooltip explains the limit.
5. **`vcodec`/`acodec` use the string `"none"` as a sentinel; `None` means unknown.**
   archive.org returns `None` for both on real video files.
6. **Sizes have three tiers** (`filesize`, `filesize_approx`, `tbr * duration`). For HLS/DASH
   formats `tbr` is often the *peak* bitrate, so those estimates read high — the model flags
   them with `filesize_unreliable` and the UI must keep saying so.
7. **FFmpeg is Homebrew's `ffmpeg-full`** (libass, libwebp, zimg), installed 2026-09-23 with
   Berk's approval. At his request the plain `ffmpeg` formula was then uninstalled and
   ffmpeg-full was `brew link --force`d, so `/opt/homebrew/bin/ffmpeg` is ffmpeg-full too. The
   keg path `/opt/homebrew/opt/ffmpeg-full/bin` is still preferred. `app/ffmpeg/binaries.py` prefers ffmpeg-full and never mixes
   ffmpeg/ffprobe from two builds; always get binaries from there, never `shutil.which`. The
   doctor detects capabilities at runtime; a feature that needs libass/libwebp must check them.
8. **Lossless vs frame-accurate cuts** (for M4): stream-copy cuts land on keyframes and will
   drift by up to a GOP; frame-accurate cuts require re-encoding. The UI must offer both and
   explain the trade-off, never silently pick one.
9. `format_id` values are de-duplicated by yt-dlp (`140-0`, `251-drc`, `247-sr`). Always key on
   the final `format_id` string, never a raw itag.
10. Playwright specs are `frontend/e2e/*.spec.cts` (`.cts`, because the package is ESM and
    `@playwright/test` is CommonJS). Screenshots land in `test-results/screenshots/`.
11. **We mux, not yt-dlp.** The worker downloads raw streams with `-f v,a1,a2` (comma) and
    `backend/app/ffmpeg/mux.py` builds the file. Do not "simplify" back to `+` and yt-dlp's
    merger: with several formats it re-fetches subtitles per format and reports a wrong subtitle
    `filepath`, and the multistreams semantics are slated to change upstream.
12. `-map_metadata -1` also drops chapter titles; see `mux.py` for the workaround.
13. The job manager's state is bound to the asyncio loop. Route handlers that touch it must be
    `async def`; never call it from a thread without `_on_loop`.
14. Offline download tests: `scripts/make_test_media.py` generates clips and `info.json`; the
    fixture URL `https://example.test/local-media` inspects them. The e2e server regenerates
    them and starts with an empty database on every run.
15. Scratch files live in `<download dir>/.vd-work/<job id>/` so a retry resumes `.part` files;
    only that directory is ever deleted, and only after the final file is in place.
16. **Filenames are untrusted input.** Use `naming.render_relative` + `naming.claim`: a title of
    `..` becomes `_`, components are trimmed to 200 bytes (APFS limit is 255), and a whole set
    of files gets one base name reserved atomically with O_EXCL placeholders. Never build an
    output path any other way.
17. **SQLite connections are not thread-safe.** The job store is used only on the event loop;
    the library has its own connection and a lock because it is also used from threads.
18. **Tests never touch Berk's folders.** An autouse fixture points `VD_DATA_DIR` and
    `VD_DOWNLOAD_DIR` at tmp dirs; fixture mode sends Trash to `simulated-trash`, and the
    folder picker and yt-dlp updater refuse to run. `scripts/check.sh` fails if the e2e server
    logged a traceback.
19. An FFmpeg input seek (`-ss`), even to 0, drops an audio file's single cover-art packet, and
    FFmpeg then exits 0 without writing anything. Check that outputs exist, not just exit codes.
20. **Never download from a sanitized/re-processed YouTube info dict.** Format URLs are finished
    lazily (the "n" JS challenge is solved at download time via callbacks sanitize_info drops),
    so extracting with one YoutubeDL and downloading with another gives HTTP 403 on every real
    YouTube video. Each pass calls `extract_info(url, download=True)` (see `_fetch`). The offline
    suite cannot catch this; run `RUN_LIVE_TESTS=1 uv run pytest -m live` after touching the
    download path.
21. Lossless (stream-copy) cuts start on the previous keyframe *and* can end a few frames late
    (B-frame reordering: 27 frames instead of 25 per 1 s piece at 25 fps). Tests state that bound;
    frame-accurate cuts are within one frame.

22. **Toolbar actions are portals.** A screen puts its toolbar buttons in
    `<ToolbarItems>` (`components/Toolbar.tsx`); they render into the window toolbar. Icons go
    through `<Icon name="sf.symbol.name">` (`components/Icon.tsx`) so the SF-style names stay in
    one map. An icon-only button needs an `aria-label` (the e2e tests find buttons by it).
23. **The native app** (`macos/`) owns the backend: `uv sync`, then `.venv/bin/python -m
    app.main` (not `uv run`, so one SIGTERM reaches the server once), spawned with posix_spawn
    in its own process group, PATH extended with Homebrew, `VD_PARENT_PID` set. The server
    shuts itself down when that parent disappears (crash, kill). On quit the app closes its
    web views first, then SIGTERM, SIGKILL after 15 s. uvicorn has
    `timeout_graceful_shutdown=2`: without it an open event stream held shutdown until the
    SIGKILL, and running workers were orphaned. If a server already answers on the port the
    app attaches to it and never stops it, but keeps checking its health: a server that stops
    answering (ours or attached) becomes a failure with a retry, never a silent "ready".
    Workers (own sessions) hold a **lifeline** (`app/workers/lifeline.py`): re-parented after
    a SIGKILL of the server, they kill their own group. The signal handler announces shutdown
    so open event streams end at once.
24. **Motion** lives in `theme.css` (the "motion" block) plus `components/motion.ts`, which
    slides every `.segmented` thumb by observing the DOM and cross-fades theme changes with view
    transitions. Everything stops under "Reduce motion". Screenshots pass
    `animations: 'disabled'`; hover a term only after the page has settled (the download plan
    grows the panel and shifts the page).
25. **A file created after an item was catalogued is never that item's file** (`_born_after`,
    macOS `st_birthtime`, which survives moves, renames, tags and Put Back). Without that rule a
    re-download of the same video, reusing a deleted file's name with identical bytes, was
    "restored" into the old record: two records, one file.
26. Help tags (`<Term>`) render into `document.body` with fixed positioning, so panels with
    `overflow: hidden` cannot clip them.
27. The e2e server runs on port 8788 (`VD_PORT`), so the suite can run while the real app is open
    on 8787.

28. **The macOS project** (`macos/VideoDownloader/`) was generated once by Apple's
    `xcrun safari-web-extension-packager` and is maintained by hand. The web extension's files
    live in `macos/extension/` and the project only references them. The UI-test target and the
    shared scheme were added by hand (the test target uses a synchronized folder, so new test
    files need no project edit). Team `V88QY49A4T`, automatic signing. The extension must stay
    sandboxed with `network.client` only; the app is deliberately not sandboxed (it will run
    Python, yt-dlp and FFmpeg).
29. **Observing the extension.** This shell cannot read the unified log (`log show` returns
    nothing), so `Logger` output is invisible here. Use the app's `--print-extension-state` flag
    (only the containing app may ask Safari) and the backend's access log
    (`uvicorn app.main:create_app --factory --log-level info`). Safari enabled the
    development-signed extension on first launch of the app, with no checkbox, and kept it
    across restarts.
30. `scripts/check.sh` now builds the app and runs its UI tests, which open the app window for
    a few seconds. Xcode attaches *any* crash report written during a UI test run to the
    result (on this Mac, CleanMyMac's); read the process name before blaming the app.
31. `tests/fixtures/media/` once lost `video_h264.mp4` while `info.json` survived (1 Oct, outside
    any session). The `test_media` fixture now rebuilds the set when any file the info dict
    points at is missing.
32. **Quick choices are computed once, in `app/ytdlp/offers.py`.** The web panel, `/api/quick`
    and (from N3) the Safari popup all read its rows and their ready-made `selection`; never
    re-derive a choice in JavaScript or Swift. A rule is saved only when the row still chosen
    at download time is one that was clicked: saving the untouched default, a preselected
    nearest match, or a default after switching output each ratchets a whole site down to
    whatever one video offered (found twice in review, in the panel and the popup).
    The audio-only defaults (`selection.DEFAULT_AUDIO_CODEC/QUALITY`) mirror the panel's
    initial `mp3`/`192`; change both together.
33. **Embedded web UI** -- *no longer used by the app since N7* (WebBridge is gone; the
    browser UI remains until N8). It was `?embedded=1`, `frontend/src/lib/embedded.ts`: no sidebar, title or
    theme (the window follows the system appearance), no notifications (the app posts them),
    and `window.vd.navigate/inspect` for the app; the page reports `ready` and route changes
    through `window.webkit.messageHandlers.vd`. **WebBridge queues every call until `ready`**:
    a script run while the page loads dies with that document (a link handed to a closed app
    was lost). `?embedded=1&route=settings` renders the settings screen alone
    (`SettingsWindow.tsx`). Incoming links (`IncomingURL`) are inspected without a click, so
    only public http(s) hosts qualify -- never loopback, the LAN, or a nested file. The native strings live in
    `macos/VideoDownloaderKit/Sources/VideoDownloaderKit/Resources/Localizable.xcstrings`
    (Turkish only; the app declares `tr`, so the system menus are Turkish too).
34. **Native UI tests run against a fixture-mode backend on port 8789** with temporary
    `VD_DATA_DIR`/`VD_DOWNLOAD_DIR`/`VD_LOG_FILE` and `VD_APPEARANCE=light|dark`. Web text is
    the element's *value* in XCUITest, and a badge after a term adds a trailing space: match
    with `BEGINSWITH`. **Screenshot windows, never `XCUIScreen.main`**: a full-screen capture
    once recorded whatever else Berk had open. `typeKey(",", .command)` does not reach the
    Settings item on this Mac (Turkish keyboard layout); tests click the menu item, and `typeText` drops the letter "i" there (any field: "bir media" arrives as "br meda"; the fixture URL `example.test/local-media` still matches by its host), so typed test strings avoid it. The runner is
    sandboxed: its scratch is under `~/Library/Containers` (it cannot write `/tmp`), so the
    backend refuses that download folder and `PUT /api/settings` fails from a UI test; change a
    setting by writing the test's own `data/settings.json` (read on every request).
35. **The Safari extension** (`macos/extension/`, plain JS, no build step): `shared.js` (also
    loaded by vitest), `background.js` (icon + link menu), `content.js` (looks for
    `<video>`/`<audio>`/manifests, tells only the background script), `popup.*`. All app access
    goes through `sendNativeMessage` -> `SafariWebExtensionHandler` -> `Relay.swift`, whose
    allowlist is the security boundary: GET health/supports/jobs, POST inspect/quick, open
    `videodownloader://inspect|show`. Nothing else (Trash, pickers, updater, settings).
    Strings: `_locales/tr/messages.json` (the extension's catalog). The e2e suite serves the
    folder at `/__test/extension/` (fixture mode only) and stubs `browser.*` as a transport.
    **Safari only loads a rebuilt extension after it is restarted**, and the extension needs
    "all websites" access, which only Berk can grant. `VD_ACCESS_LOG=1` turns on the request
    log for debugging it; never leave it on (it records the pages he visits). The handler uses
    an ephemeral, cache-less URLSession and every `/api/*` answer is `Cache-Control: no-store`:
    the shared session had kept a Cache.db of visited page addresses. The relay refuses
    inspect/quick bodies whose `url` is this Mac or the LAN (`LocalHost.swift`, shared with
    `IncomingURL`; mirrored in `shared.js isLocal`).
36. **Berk's Safari session** (`app/browser_session.py`, `app/workers/session.py`), his decision
    2026-10-13, his own account: only an AGE_RESTRICTED/LOGIN_REQUIRED answer *for a YouTube
    URL* is retried once with it; the worker gets only the `youtube.com` cookies loaded into its
    in-memory jar (never yt-dlp's `cookiesfrombrowser`, which loads every site's cookies);
    info.json is scrubbed of the per-format `cookies` field; the job carries
    `["safari", path]` and shows `used_session`; turning the setting off stops it in the cache,
    new jobs and retries. Reading the store needs Full Disk Access for VideoDownloader.app
    (Terminal when the server was started there). `errors.classify` drops URLs first: an
    address containing "login" once turned an unsupported page into LOGIN_REQUIRED, which
    would have sent the session to that site. Tests set VD_SAFARI_COOKIES (conftest), so no
    test ever reads the real store.
37. **Native screens** (every screen since N7) live in `VideoDownloaderKit/Views/`. They call the same endpoints
    as the web screen, through `APIClient`. Backend codes and states are worded from the native
    catalog (`error.<CODE>.title/body`, `queue.status.*`, `doctor.*`), a copy of `tr.ts` that
    `frontend/src/nativeStrings.test.ts` keeps equal: change both together. Decode `/api/doctor`
    with `JSON.plain`: `convertFromSnakeCase` also rewrites *dictionary keys*
    (`ffmpeg_path` -> `ffmpegPath`). Keys built at run time are not seen by the catalog scan;
    list new families in `LocalizationTests.everyStateTheScreensNameIsTranslated`. On macOS a
    grouped `Form` puts a bare button row under the box (as System Settings does).
38. **SwiftUI pitfalls met in N5.** An `accessibilityIdentifier` on a container that is not an
    accessibility element is copied onto *every child*, replacing their own identifiers: give
    such containers `.accessibilityElement(children: .contain)` first. A `Form` inside a
    `ScrollView` collapses to nothing (the track picker uses plain sections). Paste commands
    reach only the focused view, so İncele makes its page focusable for ⌘V. XCUITest walks the
    whole accessibility tree for every query: a big result (the multi-audio fixture) made each
    step take ~40 s until table rows became one element each (`.combine`). The native panel's
    remembered quick choices live in UserDefaults (`vd-quick-rules`), apart from the web page's
    localStorage and the Safari popup's storage; with `VD_DATA_DIR` set (every test) they go to
    `<data>/native-quick-rules.json` instead, because UI tests run this same bundle and would
    otherwise read and ratchet Berk's real rules. The panel's state (`DownloadPlanner`) lives in
    `Inspector`, not in a view's `@State`: leaving İncele must not reset the tracks. Fixture mode
    counts as "unknown, so no remote images" until `/api/health` has answered. **Tests never load remote images**: the app
    shows none against a fixture-mode backend (`remoteImages`), and Playwright sends every
    request outside this Mac to a closed proxy port (the suite used to fetch i.ytimg.com).
    The paste UI test puts Berk's pasteboard back afterwards.
39. **AppKit aborts on a layout feedback loop** ("more Update Constraints in Window passes than
    there are views"; the crash names `SplitViewChildController … didUpdateMinSize`). In a split
    view column, outside a scroll view, never let a size depend on itself: no text pinned to its
    own height (`fixedSize(horizontal: false, vertical: true)`, as `NoticeRow` does -- fine
    inside a ScrollView/List/Form), no `ViewThatFits` choosing by width, no toolbar item that
    changes size (a spinner swapped for a label). A sideways ScrollView needs a fixed height.
    Other N6 lessons: a `confirmationDialog` clears its `isPresented` binding *before* the
    button's action runs -- act on the item it passes, not on state; a segmented control drawn
    icon-only in the toolbar is named after its SF symbol ("Izgara Görüntüsü"), so give each
    segment an `accessibilityLabel`; macOS's Turkish name for Quick Look is "Göz At"; the SPA's
    `index.html` is served `no-cache` (the app's web view kept an old one, and its old scripts,
    after a rebuild); UI tests pass `-ApplePersistenceIgnoreState YES` (window restoration is
    Berk's: after a crash it brought the app up with no window) and use an ephemeral web data
    store. A failing UI test's hierarchy dump includes the Apple menu's recent items: never copy
    those dumps anywhere.

40. **Stüdyo cuts on frames** (Berk's request, 2026-10-13). The native timeline works on a
    `TimeGrid`: the source's own frames (`frame_rate` from the probe), milliseconds for sound.
    Pieces go to the backend as `start_frame`/`end_frame` ([first kept, first dropped)); the
    backend converts with the *source's* rate, **counted from the video's own first frame**
    (`video_start`: an MKV's picture can start after its sound, an MPEG-TS far from 0), and the
    player's clock puts frame 0 there too (`TimeGrid.origin`). A **variable frame rate** source
    has no frame grid (`frame_rate` null): it is cut by time, to the millisecond -- frame numbers
    of a nominal rate were measured to cost a joined cut a third of its picture. Frame-accurate:
    a coarse input `-ss` 10 s early (an MPEG-TS lands only roughly), then an exact output `-ss`
    one millisecond (at most a quarter frame) before the first frame, `-frames:v N`, `-t N/fps`
    -- half a frame early was measured to shift the output by a frame, lose the last one and
    put the sound 20 ms ahead.
    Joined pieces use `trim=start_frame:end_frame`. Lossless: `-ss` half a frame *after* the
    chosen keyframe (a copy starts at the keyframe at or before -ss), and the UI snaps the
    start to keyframes (`/api/studio/keyframes`), so it shows where the cut really starts.
    `tests/test_studio_frames.py` proves first/last frames by comparing pixels with the
    neighbours. **AVFoundation** plays neither MKV/WebM nor VP9 (and AV1 only "playable" without
    frames): `/api/studio/preview` makes a copy (H.264/HEVC copied, else VideoToolbox H.264;
    AAC/ALAC copied, else AAC -- an .m4a refuses MP3; `-fps_mode passthrough`) in
    `<data>/preview-cache`, 3 GB cap (an evicted copy is made again); frame N of the copy is
    frame N of the source. Its status is `POST /api/studio/preview/status`: no GET names a
    local file (GETs skip the cross-site check), and an unknown `/api/*` GET is a 404, not the
    page. Seeks aim at the middle of a frame with zero tolerance. **Ayarlar** applies at
    once (a refused switch springs back via `commit(undo:)`); in UI tests every save is refused
    (the runner's download folder is under ~/Library), which the test uses to check the error.

## Rules

- **Never delete, skip, weaken or `xfail` a test to make the suite pass.** Fix the code.
- Studio operations write new files. Nothing overwrites or deletes the user's media without an
  explicit confirmation step in the UI, and deletes go to the Trash.
- Before any system-wide install (Homebrew, global npm), stop and ask Berk.
