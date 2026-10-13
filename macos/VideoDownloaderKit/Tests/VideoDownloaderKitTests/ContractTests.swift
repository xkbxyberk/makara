import Foundation
import Testing
@testable import VideoDownloaderKit

/// The backend's real responses (written by tests/test_api_samples.py) decode into the
/// app's models. If the API changes shape, this fails before the app does.
struct ContractTests {
    static let samples = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
        .appending(path: "tests/fixtures/api")

    func sample(_ name: String) throws -> Data {
        try Data(contentsOf: Self.samples.appending(path: "\(name).json"))
    }

    @Test func health() throws {
        let health = try JSON.decoder.decode(Health.self, from: sample("health"))
        #expect(health == Health(ok: true, fixtureMode: true))
    }

    @Test func settings() throws {
        let settings = try JSON.decoder.decode(AppSettings.self, from: sample("settings"))
        #expect(settings.defaultMode == "mkv")
        #expect(settings.notifications)
    }

    @Test func jobs() throws {
        let jobs = try JSON.decoder.decode([Job].self, from: sample("jobs"))
        let job = try #require(jobs.first)
        #expect(job.status == .done)
        #expect(job.title == "Local test clip")
        #expect(job.outputFiles.count == 1)
        #expect(job.usedSession == false)
        #expect(job.warnings == [])
        #expect(job.errorRaw == nil)
        #expect(!job.isIndeterminate)
    }

    @Test func doctor() throws {
        let report = try JSON.plain.decode(DoctorReport.self, from: sample("doctor"))
        #expect(report.checks.map(\.id) == ["yt_dlp", "js_runtime", "ffmpeg", "safari_session"])
        let ffmpeg = try #require(report.checks.first { $0.id == "ffmpeg" })
        // Keys exactly as sent: the snake-case decoder would have made these "ffmpegPath", "videotoolboxH264".
        #expect(ffmpeg.values["ffmpeg_path"] != nil)
        guard case .object(let capabilities)? = ffmpeg.values["capabilities"] else {
            Issue.record("no capabilities")
            return
        }
        #expect(capabilities["videotoolbox_h264"] == .bool(true))
        #expect(Set(capabilities.keys).isSubset(of: Set(Capabilities.order)), "a capability the native screen has no place for")
        let runtime = try #require(report.checks.first { $0.id == "js_runtime" })
        guard case .array(let found)? = runtime.values["found"], case .object(let first)? = found.first else {
            Issue.record("no runtimes")
            return
        }
        #expect(first["version"]?.string != nil)
        let session = try #require(report.checks.first { $0.id == "safari_session" })
        #expect(session.values["state"] == .string("unavailable"))  // tests never see Berk's session
        #expect(session.fix.kind == "none")
    }

    @Test func jobEventDecodesThroughTheSSEPath() throws {
        let text = String(decoding: try sample("event-job"), as: UTF8.self)
        guard case .job(let job)? = ServerEvent.decode(name: "job", data: text) else {
            Issue.record("not a job event")
            return
        }
        #expect(job.status == .done)
    }

    @Test func errorBody() throws {
        let body = try JSON.decoder.decode(APIErrorBody.self, from: sample("error"))
        #expect(body.error.code == "QUICK_NEEDS_SOURCE")
    }

    @Test func supports() throws {
        let answer = try JSON.decoder.decode(Supports.self, from: sample("supports"))
        #expect(answer.supported)
    }

    @Test func everySampleIsCoveredByATest() throws {
        let names = try FileManager.default.contentsOfDirectory(atPath: Self.samples.path)
            .filter { $0.hasSuffix(".json") }.sorted()
        #expect(names == ["doctor.json", "error.json", "event-job.json", "health.json", "inspect-playlist.json", "inspect-video.json",
                          "jobs.json", "library.json", "plan.json", "scan.json", "settings.json", "supports.json"])
    }

    @Test func inspectedVideo() throws {
        guard case .video(let model) = try JSON.decoder.decode(InspectResult.self, from: sample("inspect-video")) else {
            Issue.record("not a video")
            return
        }
        #expect(model.media.title?.isEmpty == false)
        #expect(!model.videoFormats.isEmpty && !model.audioLanguages.isEmpty)
        #expect(model.audioLanguages.contains { $0.role == "original" })
        #expect(!model.subtitles.autoTranslated.isEmpty)
        // `compat_mp4` keys decode (the snake-case strategy maps them onto compatMp4).
        #expect(model.defaults.compatMp4.videoFormatId != nil)
        let offer = try #require(model.offers.video.first)
        #expect(offer.outputs.compatMp4.vcodecLabel == "H.264")
        #expect(!model.offers.audio.isEmpty)
        #expect(model.commands.suggested.hasPrefix("yt-dlp "))
    }

    @Test func inspectedPlaylist() throws {
        guard case .playlist(let model) = try JSON.decoder.decode(InspectResult.self, from: sample("inspect-playlist")) else {
            Issue.record("not a playlist")
            return
        }
        #expect(model.entryCount > 0 && !model.entries.isEmpty)
        #expect(model.entries.first?.url != nil)
    }

    @Test func library() throws {
        let page = try JSON.decoder.decode(LibraryPage.self, from: sample("library"))
        let item = try #require(page.items.first)
        #expect(item.title == "Local test clip")
        #expect(item.status == "ok" && !item.isMissing)
        #expect(item.tracks.audio.first?.language == "eng")
        #expect(item.tracks.video.first?.height == 360)
        #expect(page.facets.count == 1 && page.facets.sites == ["Generic"])
        let scan = try JSON.decoder.decode(ScanResult.self, from: sample("scan"))
        #expect(scan.checked == 1 && scan.missing == 0)
    }

    @Test func libraryQueryLeavesEmptyFieldsOut() {
        var query = LibraryQuery()
        #expect(query.items == [URLQueryItem(name: "sort", value: "added")])
        #expect(!query.isFiltered)
        query.search = "klip"
        query.status = "missing"
        #expect(query.items.map(\.name) == ["search", "status", "sort"])
        #expect(query.isFiltered)
    }

    @Test func plan() throws {
        let plan = try JSON.plain.decode(Plan.self, from: sample("plan"))
        #expect(!plan.blocking)
        #expect(plan.filename?.hasSuffix(".mp4") == true)
        #expect(plan.notices.first?.params["codec"] == .string("AV1"))
        #expect(plan.notices.contains { $0.params["format_id"] == .string("137") })  // keys as sent
    }

    @Test func aRunningJobSaysWhetherItHasAPercentage() throws {
        func job(_ stage: String, _ progress: Double) throws -> Job {
            let json = #"{"id":"x","kind":"download","status":"running","stage":"\#(stage)","progress":\#(progress),"output_files":[],"speed":1048576,"eta":75,"item_index":2,"item_count":5,"used_session":true,"warnings":[{"code":"SUBTITLE_SKIPPED","key":"tr"}]}"#
            return try JSON.decoder.decode(Job.self, from: Data(json.utf8))
        }
        let downloading = try job("downloading", 0.4)
        #expect(!downloading.isIndeterminate)
        #expect(downloading.itemIndex == 2 && downloading.itemCount == 5)
        #expect(downloading.usedSession == true)
        #expect(downloading.warnings == [JobWarning(code: "SUBTITLE_SKIPPED", key: "tr")])
        #expect(try job("downloading", 0).isIndeterminate)
        #expect(try job("postprocessing", 0.9).isIndeterminate)
    }

    @Test func anUnknownJobStatusDoesNotBreakDecoding() throws {
        let json = #"{"id":"x","kind":"download","status":"paused","output_files":[]}"#
        let job = try JSON.decoder.decode(Job.self, from: Data(json.utf8))
        #expect(job.status == .unknown)
    }
}
