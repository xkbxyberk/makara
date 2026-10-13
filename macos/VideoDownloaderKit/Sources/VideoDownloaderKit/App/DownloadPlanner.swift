import Foundation
import Observation

/// The download panel's state and rules, apart from its views (the native twin of the web
/// page's `DownloadPanel`): the output, the tracks chosen for each output, the quick choice
/// clicked, and the plan the backend computed for exactly this selection.
@MainActor
@Observable
public final class DownloadPlanner {
    public static let codecs = ["mp3", "m4a", "opus", "flac", "wav"]
    public static let lossy: Set<String> = ["mp3", "m4a", "opus"]
    public static let qualities = ["320", "256", "192", "128"]

    public let model: VideoModel
    public let remembered: Bool

    public private(set) var mode: Mode
    public private(set) var tracks: [Mode: TrackSelection]
    public var audioCodec: String
    public var audioQuality = "192"
    public var extras = Selection.Extras()
    /// nil: the settings' template.
    public private(set) var template: String?
    public private(set) var defaultTemplate = ""

    public private(set) var plan: Plan?
    /// The selection the plan on screen was computed for. İndir stays disabled until they
    /// match, so a job never starts on a selection whose warnings were not shown.
    public private(set) var planFor: Selection?
    public private(set) var failure: APIError?
    public private(set) var submitting = false
    /// The selection last queued. "Kuyruğa eklendi" holds until the selection changes, and the
    /// same selection is not queued twice (⌘↵ held down repeats).
    public private(set) var queuedFor: Selection?
    public var queued: Bool { queuedFor != nil && queuedFor == selection }
    /// The track picker is open (kept here so it survives a trip to another screen).
    public var pickerOpen = false

    /// Only a quick choice Berk actually clicked becomes the rule for the next video: neither the
    /// untouched default nor a preselected match (the match for a 1080p rule on a video that tops
    /// out at 360p is the 360p row, and saving it would cap every later video at 360p).
    public private(set) var chosenId: String?
    /// A remembered choice already decided the output; the settings' default must not override it.
    @ObservationIgnored private var touchedMode: Bool

    public init(model: VideoModel, remembered: Bool) {
        self.model = model
        self.remembered = remembered
        var tracks = Dictionary(uniqueKeysWithValues: Mode.allCases.map { ($0, model.defaults[$0]) })
        var mode = Mode.mkv
        var codec = "mp3"
        var started = false
        // The quick choice the server preselected for a remembered rule, as the first state.
        if remembered, let pre = model.offers.preselected {
            if let row = model.offers.video.first(where: { $0.id == pre.offerId }),
               let output = pre.output.flatMap(Mode.init(rawValue:)) {
                let pick = row.output(for: output).selection
                mode = output
                tracks[output] = TrackSelection(videoFormatId: pick.videoFormatId, audioFormatIds: pick.audioFormatIds,
                                                subtitleKeys: pick.subtitleKeys)
                started = true
            } else if let row = model.offers.audio.first(where: { $0.id == pre.offerId }) {
                mode = .audio
                tracks[.audio] = TrackSelection(videoFormatId: nil, audioFormatIds: row.selection.audioFormatIds, subtitleKeys: [])
                codec = row.format
                started = true
            }
        }
        self.mode = mode
        self.tracks = tracks
        self.audioCodec = codec
        self.touchedMode = started
    }

    /// The settings' output and file name template, unless Berk already picked an output here.
    public func apply(settings: AppSettings) {
        defaultTemplate = settings.filenameTemplate
        if !touchedMode, let preferred = Mode(rawValue: settings.defaultMode) { mode = preferred }
    }

    public func choose(_ next: Mode) {
        touchedMode = true
        mode = next
    }

    public var current: TrackSelection { tracks[mode] ?? model.defaults[mode] }

    public var selection: Selection {
        let audioOnly = mode == .audio
        return Selection(
            inspectId: model.inspectId, mode: mode,
            videoFormatId: audioOnly ? nil : current.videoFormatId,
            audioFormatIds: current.audioFormatIds,
            subtitleKeys: audioOnly ? [] : current.subtitleKeys,
            audioCodec: audioOnly ? audioCodec : nil,
            audioQuality: audioOnly && Self.lossy.contains(audioCodec) ? audioQuality : nil,
            filenameTemplate: template, extras: extras)
    }

    public var planIsCurrent: Bool { plan != nil && planFor == selection }
    public var canSubmit: Bool { planIsCurrent && plan?.blocking == false && !submitting && !queued }

    public func update(_ change: (inout TrackSelection) -> Void) {
        var next = current
        change(&next)
        tracks[mode] = next
    }

    // ---- the template -----------------------------------------------------------------------

    public var templateText: String { template ?? defaultTemplate }

    /// Typing the settings' own template back means "the default" again.
    public func setTemplate(_ value: String) { template = value == defaultTemplate ? nil : value }
    public func resetTemplate() { template = nil }

    // ---- quick choices ----------------------------------------------------------------------

    public enum QuickRow: Identifiable, Equatable {
        case video(VideoOffer)
        case audio(AudioOffer)

        public var id: String {
            switch self {
            case .video(let row): row.id
            case .audio(let row): row.id
            }
        }
    }

    public var quickRows: [QuickRow] {
        switch mode {
        case .audio: model.offers.audio.map(QuickRow.audio)
        case .separate: []
        case .mkv, .compatMp4: model.offers.video.map(QuickRow.video)
        }
    }

    /// The row the current tracks amount to, if any.
    public var activeRow: QuickRow? {
        quickRows.first { row in
            switch row {
            case .video(let offer): (mode == .mkv || mode == .compatMp4) && offer.output(for: mode).videoFormatId == current.videoFormatId
            case .audio(let offer): offer.format == audioCodec && current.audioFormatIds.first == offer.formatId
            }
        }
    }

    public var rememberedId: String? { remembered ? model.offers.preselected?.offerId : nil }

    public func apply(_ row: QuickRow) {
        switch row {
        case .video(let offer):
            guard mode == .mkv || mode == .compatMp4 else { return }
            let pick = offer.output(for: mode).selection
            update {
                $0.videoFormatId = pick.videoFormatId
                $0.audioFormatIds = pick.audioFormatIds  // subtitles stay as chosen
            }
        case .audio(let offer):
            update { $0.audioFormatIds = offer.selection.audioFormatIds }
            audioCodec = offer.format
            if let quality = offer.selection.audioQuality { audioQuality = quality }
        }
        chosenId = row.id
    }

    /// What a download now would remember for this site: only a row Berk clicked that the
    /// tracks still amount to -- never the untouched default, a preselected match, or a click
    /// undone by changing the tracks afterwards.
    public var ruleToSave: QuickRule? {
        guard let row = activeRow, row.id == chosenId else { return nil }
        return Self.rule(for: row, mode: mode)
    }

    static func rule(for row: QuickRow, mode: Mode) -> QuickRule {
        switch row {
        case .video(let offer):
            var rule = offer.rule
            rule.output = mode == .compatMp4 ? "compat_mp4" : "mkv"
            return rule
        case .audio(let offer):
            return offer.rule
        }
    }

    // ---- the track picker -------------------------------------------------------------------

    public var videos: [VideoFormat] { model.videoFormats + model.muxedFormats }

    public func chosen(in group: AudioLanguageGroup) -> AudioFormat? {
        group.tracks.first { current.audioFormatIds.contains($0.formatId) }
    }

    /// One language on or off, or another variant of it. The original (or first chosen)
    /// language stays first: it becomes the default track.
    public func setGroup(_ group: AudioLanguageGroup, to formatId: String?) {
        let others = current.audioFormatIds.filter { id in !group.tracks.contains { $0.formatId == id } }
        if mode == .audio {
            update { $0.audioFormatIds = formatId.map { [$0] } ?? [] }
            return
        }
        let chosen = chosen(in: group)
        update { selection in
            if let formatId {
                if let chosen {
                    selection.audioFormatIds = selection.audioFormatIds.map { $0 == chosen.formatId ? formatId : $0 }
                } else {
                    selection.audioFormatIds = others + [formatId]
                }
            } else {
                selection.audioFormatIds = others
            }
        }
    }

    public func toggleSubtitle(_ key: String) {
        update { selection in
            if selection.subtitleKeys.contains(key) {
                selection.subtitleKeys.removeAll { $0 == key }
            } else {
                selection.subtitleKeys.append(key)
            }
        }
    }

    // ---- plan and download ------------------------------------------------------------------

    /// Ask the backend what this selection will produce. The view calls it a moment after
    /// each change (a newer call replaces an older one: SwiftUI cancels the older task).
    public func refreshPlan(client: APIClient) async {
        let asked = selection
        do {
            let next = try await client.plan(asked)
            guard !Task.isCancelled else { return }
            plan = next
            planFor = asked
            failure = nil
        } catch {
            guard !Task.isCancelled else { return }
            failure = APIError.from(error)
        }
    }

    public func submit(client: APIClient, rules: QuickRules) async {
        guard canSubmit else { return }
        submitting = true
        defer { submitting = false }
        let asked = selection
        let remember = ruleToSave
        do {
            _ = try await client.createJob(asked)
            queuedFor = asked
            // Remember the shape of this choice for the next video from the same site.
            if let remember { rules.save(remember, for: model.sourceUrl) }
        } catch {
            failure = APIError.from(error)
        }
    }
}
