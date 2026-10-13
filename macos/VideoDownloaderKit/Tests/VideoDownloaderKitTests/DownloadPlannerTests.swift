import Foundation
import Testing
@testable import VideoDownloaderKit

/// The download panel's rules against the real inspect answer for the multi-audio fixture
/// (tests/fixtures/api/inspect-video.json), mirroring the web panel's.
@MainActor
struct DownloadPlannerTests {
    static func video() throws -> VideoModel {
        let data = try Data(contentsOf: ContractTests.samples.appending(path: "inspect-video.json"))
        guard case .video(let model) = try JSON.decoder.decode(InspectResult.self, from: data) else {
            throw CocoaError(.coderReadCorrupt)
        }
        return model
    }

    static func settings(mode: String) throws -> AppSettings {
        let json = #"{"download_dir":"/x","filename_template":"%(title)s","concurrency":2,"default_mode":"\#(mode)","clipboard_watch":false,"notifications":true}"#
        return try JSON.decoder.decode(AppSettings.self, from: Data(json.utf8))
    }

    @Test func startsFromTheDefaultsAndTheSettingsOutput() throws {
        let model = try Self.video()
        let planner = DownloadPlanner(model: model, remembered: false)
        #expect(planner.mode == .mkv)
        #expect(planner.current == model.defaults.mkv)
        planner.apply(settings: try Self.settings(mode: "compat_mp4"))
        #expect(planner.mode == .compatMp4)
        #expect(planner.templateText == "%(title)s")
        #expect(planner.selection.filenameTemplate == nil)  // the default template is not sent
    }

    @Test func aRememberedChoiceDecidesTheOutputOverTheSettings() throws {
        let model = try Self.video()
        let pre = try #require(model.offers.preselected)
        let planner = DownloadPlanner(model: model, remembered: true)
        #expect(planner.mode.rawValue == pre.output)
        planner.apply(settings: try Self.settings(mode: "audio"))
        #expect(planner.mode.rawValue == pre.output)
        #expect(planner.rememberedId == pre.offerId)
    }

    @Test func aQuickChoiceSetsTheTracksButKeepsTheSubtitles() throws {
        let model = try Self.video()
        let planner = DownloadPlanner(model: model, remembered: false)
        planner.toggleSubtitle("en")  // off
        let lowest = try #require(model.offers.video.last)
        planner.apply(.video(lowest))
        #expect(planner.current.videoFormatId == lowest.outputs.mkv.videoFormatId)
        #expect(planner.current.audioFormatIds == lowest.outputs.mkv.selection.audioFormatIds)
        #expect(!planner.current.subtitleKeys.contains("en"))
        #expect(planner.activeRow?.id == lowest.id)
        #expect(planner.chosenId == lowest.id)
    }

    @Test func audioOnlySendsNoVideoOrSubtitlesAndAQualityOnlyForLossy() throws {
        let planner = DownloadPlanner(model: try Self.video(), remembered: false)
        planner.choose(.audio)
        #expect(planner.selection.videoFormatId == nil)
        #expect(planner.selection.subtitleKeys == [])
        #expect(planner.selection.audioCodec == "mp3")
        #expect(planner.selection.audioQuality == "192")
        planner.audioCodec = "flac"
        #expect(planner.selection.audioQuality == nil)
    }

    @Test func languagesKeepTheirOrderAndAudioOnlyHasOne() throws {
        let model = try Self.video()
        let planner = DownloadPlanner(model: model, remembered: false)
        let original = try #require(planner.current.audioFormatIds.first)
        let dub = try #require(model.audioLanguages.first { group in !group.tracks.contains { $0.formatId == original } })
        planner.setGroup(dub, to: dub.tracks.first?.formatId)
        #expect(planner.current.audioFormatIds.first == original)  // the original stays the default track
        #expect(planner.current.audioFormatIds.count == 2)
        // Another variant of the same language replaces it in place.
        if dub.tracks.count > 1 {
            planner.setGroup(dub, to: dub.tracks[1].formatId)
            #expect(planner.current.audioFormatIds == [original, dub.tracks[1].formatId])
        }
        planner.setGroup(dub, to: nil)
        #expect(planner.current.audioFormatIds == [original])
        planner.choose(.audio)
        planner.setGroup(dub, to: dub.tracks.first?.formatId)
        #expect(planner.current.audioFormatIds == [dub.tracks.first?.formatId])
    }

    @Test func eachOutputKeepsItsOwnTracks() throws {
        let model = try Self.video()
        let planner = DownloadPlanner(model: model, remembered: false)
        planner.toggleSubtitle("tr")
        planner.choose(.compatMp4)
        #expect(planner.current == model.defaults.compatMp4)
        planner.choose(.mkv)
        #expect(!planner.current.subtitleKeys.contains("tr"))
    }

    @Test func typingTheDefaultTemplateBackMeansTheDefault() throws {
        let planner = DownloadPlanner(model: try Self.video(), remembered: false)
        planner.apply(settings: try Self.settings(mode: "mkv"))
        planner.setTemplate("%(id)s")
        #expect(planner.selection.filenameTemplate == "%(id)s")
        planner.setTemplate("%(title)s")
        #expect(planner.selection.filenameTemplate == nil)
    }

    /// The ratchet the review found twice on the web: only a clicked row becomes the site's rule.
    @Test func onlyAClickedQuickChoiceIsRemembered() throws {
        let model = try Self.video()
        // The untouched default matches a row, but nothing was clicked.
        let untouched = DownloadPlanner(model: model, remembered: false)
        #expect(untouched.activeRow != nil)
        #expect(untouched.ruleToSave == nil)
        // A remembered preselection is not a click either.
        #expect(DownloadPlanner(model: model, remembered: true).ruleToSave == nil)
        // A click is, with the output it is downloaded in.
        let planner = DownloadPlanner(model: model, remembered: false)
        let row = try #require(model.offers.video.dropFirst().first)
        planner.apply(.video(row))
        #expect(planner.ruleToSave?.height == row.height)
        #expect(planner.ruleToSave?.output == "mkv")
        // Switching output: that output's own tracks (its 1080p default) are not the 720p click.
        planner.choose(.compatMp4)
        #expect(planner.activeRow?.id != row.id)
        #expect(planner.ruleToSave == nil)
        // A click undone by picking another video track by hand is no longer the choice.
        planner.choose(.mkv)
        let other = try #require(planner.videos.first { $0.formatId != row.outputs.mkv.videoFormatId && !model.offers.video.map(\.outputs.mkv.videoFormatId).contains($0.formatId) })
        planner.update { $0.videoFormatId = other.formatId }
        #expect(planner.ruleToSave == nil)
    }

    /// The panel's state lives with the result, so leaving İncele and coming back keeps it.
    @Test func theInspectorKeepsThePanelOfTheResultOnShow() throws {
        let model = try Self.video()
        let inspector = Inspector(client: { APIClient(port: 1) }, rules: QuickRules(store: LocalStore(folder: FileManager.default.temporaryDirectory.appending(path: "vd-\(UUID())"))))
        inspector.phase = .ready(.video(model), remembered: false)
        let planner = try #require(inspector.planner)
        planner.toggleSubtitle("tr")
        planner.pickerOpen = true
        inspector.phase = .ready(.video(model), remembered: false)  // the same result again
        #expect(inspector.planner === planner)
        inspector.phase = .loading("https://example.test/other")
        #expect(inspector.planner == nil)
    }

    @Test func theSelectionIsSentAsTheBackendNamesIt() throws {
        let planner = DownloadPlanner(model: try Self.video(), remembered: false)
        let json = try #require(try JSONSerialization.jsonObject(with: JSON.encoder.encode(planner.selection)) as? [String: Any])
        #expect(Set(json.keys) == ["inspect_id", "mode", "video_format_id", "audio_format_ids", "subtitle_keys",
                                   "audio_codec", "audio_quality", "filename_template", "extras"])
        #expect(json["audio_codec"] is NSNull)  // null, not missing
        let extras = try #require(json["extras"] as? [String: Bool])
        #expect(extras == ["thumbnail": true, "thumbnail_file": false, "description": false, "info_json": false])
    }
}

struct QuickRulesTests {
    func store() -> QuickRules {
        let name = "vd-tests-\(UUID().uuidString)"
        return QuickRules(store: LocalStore(defaults: UserDefaults(suiteName: name)!))
    }

    @Test func oneRulePerSiteWithAliases() {
        let rules = store()
        rules.save(QuickRule(kind: "video", height: 1080, output: "mkv"), for: "https://www.youtube.com/watch?v=a")
        #expect(rules.load(for: "https://youtu.be/b")?.height == 1080)
        #expect(rules.load(for: "https://m.youtube.com/watch?v=c")?.height == 1080)
        #expect(rules.load(for: "https://vimeo.com/1") == nil)
        #expect(QuickRules.site(of: "not a url") == nil)
    }

    @Test func testsKeepTheirRulesInTheirOwnDataFolder() throws {
        let dir = FileManager.default.temporaryDirectory.appending(path: "vd-rules-\(UUID())")
        let rules = QuickRules(store: .forEnvironment(["VD_DATA_DIR": dir.path]))
        rules.save(QuickRule(kind: "audio", format: "opus"), for: "https://www.youtube.com/watch?v=a")
        #expect(FileManager.default.fileExists(atPath: dir.appending(path: "native-vd-quick-rules.json").path))
        #expect(QuickRules(store: .forEnvironment(["VD_DATA_DIR": dir.path])).load(for: "https://youtu.be/b")?.format == "opus")
        try? FileManager.default.removeItem(at: dir)
    }

    /// A value that is not an object (a string, a number) once crashed every inspect: serialising
    /// it raises an Objective-C exception that `try?` cannot catch.
    @Test func aValueThatIsNotARuleIsSkipped() throws {
        let dir = FileManager.default.temporaryDirectory.appending(path: "vd-rules-\(UUID())")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let file = dir.appending(path: "native-vd-quick-rules.json")
        try Data(#"{"youtube.com": "1080p", "vimeo.com": 3, "dailymotion.com": {"kind": "video", "height": 720}}"#.utf8).write(to: file)
        let rules = QuickRules(store: LocalStore(folder: dir))
        #expect(rules.load(for: "https://youtube.com/watch?v=a") == nil)
        #expect(rules.load(for: "https://dailymotion.com/video/x")?.height == 720)
        try? FileManager.default.removeItem(at: dir)
    }

    @Test func aDamagedRuleIsNoRule() {
        let rules = store()
        rules.save(QuickRule(kind: "video", height: 99_999), for: "https://vimeo.com/1")
        #expect(rules.load(for: "https://vimeo.com/2") == nil)
        rules.save(QuickRule(kind: "audio", format: "flac"), for: "https://vimeo.com/1")
        #expect(rules.load(for: "https://vimeo.com/2") == nil)  // only opus/m4a/mp3 are quick choices
    }
}

struct NoticeTextTests {
    @Test func paramsFallbacksAndUpperCase() throws {
        let data = try Data(contentsOf: ContractTests.samples.appending(path: "plan.json"))
        let plan = try JSON.plain.decode(Plan.self, from: data)
        let texts = plan.notices.map(noticeText)
        #expect(texts[0].hasPrefix("AV1 görüntü QuickTime’da oynamaz"))
        #expect(texts[1].contains("1080p H.264"))
        #expect(texts[2].hasPrefix("Opus ses AAC’ye"))
        #expect(Format.notice("{codec|Bu} x", [:]) == "Bu x")
        #expect(Format.notice("{codec|Ses} → {target^}.", ["target": .string("mp3")]) == "Ses → MP3.")
        #expect(noticeText(Plan.Notice(code: "SOMETHING_NEW", level: "info", params: [:])) == "SOMETHING_NEW")
    }

    @Test func languageNamesAreTurkish() {
        #expect(Format.language("en") == "İngilizce")
        #expect(Format.language("en-desc") == "İngilizce")
        #expect(Format.language(nil) == L("app.unknown"))
    }
}
