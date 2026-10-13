import Foundation
import Testing
@testable import VideoDownloaderKit

/// Every key the code asks for exists in the catalog: a missing one would show as ⟦key⟧.
struct LocalizationTests {
    static let sources = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .appending(path: "Sources/VideoDownloaderKit")

    @Test func everyKeyUsedInTheSourcesIsTranslated() throws {
        let catalog = try JSONSerialization.jsonObject(with: Data(contentsOf: Self.sources.appending(path: "Resources/Localizable.xcstrings"))) as? [String: Any]
        let keys = Set(((catalog?["strings"] as? [String: Any]) ?? [:]).keys)
        let pattern = try Regex(#"L\("([a-zA-Z0-9_.]+)""#)
        var used = Set<String>()
        let app = Self.sources.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appending(path: "VideoDownloader/VideoDownloader")
        let files = [Self.sources, app].flatMap {
            FileManager.default.enumerator(at: $0, includingPropertiesForKeys: nil)?
                .compactMap { $0 as? URL }.filter { $0.pathExtension == "swift" } ?? []
        }
        for file in files {
            for match in try String(contentsOf: file, encoding: .utf8).matches(of: pattern) {
                if let key = match.output[1].substring { used.insert(String(key)) }
            }
        }
        #expect(!used.isEmpty)
        #expect(used.subtracting(keys).sorted() == [])
        for key in used { #expect(!L(key).hasPrefix("⟦"), "\(key)") }
    }

    /// Keys built at run time (`queue.status.\(status)`) that the scan above cannot see.
    @MainActor @Test func everyStateTheScreensNameIsTranslated() {
        var keys: [String] = []
        for status in ["queued", "running", "done", "failed", "cancelled"] { keys.append("queue.status.\(status)") }
        for stage in ["queued", "starting", "preparing", "downloading", "postprocessing", "finalizing", "retrying", "cancelling"] {
            keys.append("queue.stage.\(stage)")
        }
        for mode in ["mkv", "compat_mp4", "separate", "audio", "studio"] { keys.append("mode.\(mode)") }
        for status in ["ok", "warn", "error"] { keys += ["doctor.status.\(status)", "doctor.checkStatus.\(status)"] }
        for check in ["yt_dlp", "js_runtime", "ffmpeg", "safari_session"] {
            keys += ["doctor.check.\(check)", "doctor.checkHelp.\(check)"]
        }
        for state in ["off", "unavailable", "no_access", "signed_out", "signed_in", "unknown"] { keys.append("doctor.session.\(state)") }
        for key in Capabilities.order { keys.append("doctor.capability.\(key)") }
        for key in CheckSection.order.values.joined() { keys.append("doctor.label.\(key)") }
        for key in ["subtitles_filter", "webp"] { keys.append("doctor.missing.\(key)") }
        for code in ["UNKNOWN", "NETWORK", "JOB_NOT_REMOVABLE", "JOBS_RUNNING", "AGE_RESTRICTED", "SESSION_NOT_ENOUGH"] {
            keys += ["error.\(code).title", "error.\(code).body"]
        }
        keys.append("queue.warning.SUBTITLE_SKIPPED")
        // İncele and the download panel (N5).
        for code in ["MKV_PLAYERS", "VIDEO_REENCODE", "COMPATIBLE_ALTERNATIVE", "AUDIO_REENCODE", "AUDIO_MODE_COPY",
                     "AUDIO_MODE_REENCODE", "LOSSLESS_FROM_LOSSY", "UNKNOWN_SELECTION"] { keys.append("download.notice.\(code)") }
        for role in ["original", "default", "dub", "descriptive", "unknown"] { keys += ["role.\(role)", "roleHelp.\(role)"] }
        for code in ["USED_SAFARI_LOGIN", "DRM_PRESENT", "DRM_MAYBE", "SIZES_ARE_ESTIMATES", "NO_JS_RUNTIME"] {
            keys.append("inspectWarning.\(code)")
        }
        for mode in Mode.allCases { keys += ["download.modeHelp.\(mode.rawValue)", "mode.\(mode.rawValue)"] }
        for codec in DownloadPlanner.codecs { keys.append("download.audioCodec.\(codec)") }
        for format in ["m4a", "opus", "mp3"] { keys.append("download.quick.format.\(format)") }
        for term in ["format", "fps", "codec", "hdr", "bitrate", "container", "manifest", "channels", "sampleRate",
                     "drm", "aiUpscaled", "drc", "muxed", "approxSize", "partialSize"] {
            keys += ["term.\(term).label", "term.\(term).body"]
        }
        for codec in ["H.264", "HEVC", "AV1", "VP9", "AAC", "Opus"] { keys.append("codec.\(codec)") }
        // Kütüphane (N6).
        for sort in ["added", "uploaded", "title", "size", "duration"] { keys.append("library.sort.\(sort)") }
        for kind in ["all", "video", "audio"] { keys.append("library.kind.\(kind)") }
        for key in keys { #expect(localizedIfPresent(key) != nil, "\(key)") }
    }

    @Test func anUnknownErrorCodeFallsBackToTheGenericOne() {
        #expect(ErrorCopy.title("NOT_A_CODE_YET") == L("error.UNKNOWN.title"))
        #expect(ErrorCopy.title("JOBS_RUNNING") != L("error.UNKNOWN.title"))
    }

    @Test func numbersReadAsOnTheWebPage() {
        #expect(Format.bytes(512) == "512 B")
        #expect(Format.bytes(1536) == "1.5 KB")
        #expect(Format.bytes(250 * 1024 * 1024) == "250 MB")
        #expect(Format.bytes(nil) == "–")
        #expect(Format.duration(75) == "1:15")
        #expect(Format.duration(3725) == "1:02:05")
        #expect(L("queue.item", 3, 12) == "3/12")
        #expect(L("queue.eta", "1:15") == "1:15 kaldı")
    }

    @Test func libraryWordsReadAsOnTheWebPage() {
        #expect(L("library.summary", 3, "1.5 MB") == "3 öğe · 1.5 MB")
        #expect(L("library.summaryMissing", 3, "1.5 MB", 1) == "3 öğe · 1.5 MB · 1 eksik")
        #expect(L("library.scanResult", 4, 1, 0, 2) == "4 öğe denetlendi · 1 dosyanın yeni yeri bulundu · 0 geri geldi · 2 eksik")
        #expect(L("libraryNative.trashBodyMany", 3).hasPrefix("Bu öğenin 3 dosyası"))
        // The catalogue stores three-letter codes (from the file's own tracks).
        let tracks = [LibraryTrack(codec: "opus", language: "eng", height: nil),
                      LibraryTrack(codec: "aac", language: "tur", height: nil),
                      LibraryTrack(codec: "aac", language: "eng", height: nil)]
        #expect(ItemInspector.languages(tracks) == "İngilizce, Türkçe")
        #expect(ItemInspector.languages([]) == L("library.noTracks"))
    }

    @MainActor @Test func theLibraryRemembersItsLayoutInItsOwnStore() {
        let folder = FileManager.default.temporaryDirectory.appending(path: "vd-store-\(UUID())")
        let librarian = Librarian(client: { APIClient(port: 1) }, store: LocalStore(folder: folder))
        #expect(librarian.layout == .grid)
        librarian.layout = .list
        #expect(Librarian(client: { APIClient(port: 1) }, store: LocalStore(folder: folder)).layout == .list)
        let before = librarian.trigger
        librarian.changed()
        #expect(librarian.trigger != before)  // the server's library event reloads the list
        try? FileManager.default.removeItem(at: folder)
    }

    @Test func portsAndCodesAreNeverDigitGrouped() {
        #expect(L("backend.reason.portBusy", 8787).hasPrefix("8787 portunu"))
        #expect(L("backend.reason.exited", 1).contains("çıkış kodu 1"))
    }
}
