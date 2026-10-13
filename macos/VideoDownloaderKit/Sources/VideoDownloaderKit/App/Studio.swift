import Foundation
import Observation

/// Stüdyo's state and rules, apart from its views: the source, the operation and its options,
/// the pieces to keep (on the source's own frame grid), and the plan the backend computed for
/// exactly this request. Kept by the app model, so a half-made cut survives a trip elsewhere.
@MainActor
@Observable
public final class Studio {
    public enum Phase: Equatable {
        case empty
        case probing
        case failed(APIError)
        case ready(StudioSource)
    }

    public enum Operation: String, CaseIterable, Identifiable, Sendable {
        case trim, audio, remux, subtitle
        public var id: String { rawValue }
        var symbol: String {
            switch self {
            case .trim: "scissors"
            case .audio: "waveform"
            case .remux: "slider.horizontal.3"
            case .subtitle: "captions.bubble"
            }
        }
    }

    public enum TrimMode: String, CaseIterable, Sendable { case accurate, lossless }

    public struct Track: Identifiable, Equatable, Sendable {
        public var id: String { "\(input)-\(stream.index)" }
        public let input: Int
        public let stream: StudioStream
        public let from: String
        public var keep = true
        public var language: String
        public var title: String
        public var isDefault: Bool
    }

    public static let codecs = ["mp3", "m4a", "opus", "flac", "wav"]
    public static let lossy: Set<String> = ["mp3", "m4a", "opus"]
    public static let bitrates = ["320", "256", "192", "128", "96"]

    public private(set) var phase: Phase = .empty
    public var operation: Operation = .trim { didSet { followName() } }

    // trim
    public private(set) var grid = TimeGrid(rate: nil, duration: 1)
    public private(set) var segments: [TrimSegment] = []
    public var active = 0
    /// Frame-accurate by default: what is selected is what is cut. Lossless stays one click away,
    /// and then the start snaps to the keyframes, so the screen still shows where it will start.
    public var trimMode: TrimMode = .accurate { didSet { if trimMode == .lossless { snapAll() } } }
    public var join = false
    /// Keyframe positions on the grid (loaded after opening a video).
    public private(set) var keyframes: [Int] = []
    public private(set) var keyframesLoaded = false

    // audio
    public var audioCodec = "mp3"
    public var bitrate = "192"
    public var sampleRate = ""
    public var channels = ""
    public var audioIndex = 0
    public var loudnorm = false

    // remux
    public var container = "mkv"
    public var tracks: [Track] = []
    public private(set) var extras: [StudioSource] = []

    // subtitle
    public var subtitleAction = "convert"
    public var subtitleTarget = "srt"
    public var offset = "0"

    // output and plan
    public var outputName = "" { didSet { if outputName != suggestedName { nameTouched = true } } }
    @ObservationIgnored private var nameTouched = false
    @ObservationIgnored private var suggestedName = ""
    public private(set) var plan: StudioPlan?
    public private(set) var planFor: String?
    public private(set) var failure: APIError?
    public private(set) var queuedFor: String?
    public private(set) var submitting = false

    @ObservationIgnored private let client: () -> APIClient
    @ObservationIgnored private var ticket = 0

    public init(client: @escaping () -> APIClient) { self.client = client }

    public var source: StudioSource? {
        if case .ready(let source) = phase { return source }
        return nil
    }

    // ---- opening ----------------------------------------------------------------------------

    public func open(path: String) { open { try await $0.studioProbe(path: path) } }
    public func open(item id: String) { open { try await $0.studioProbe(item: id) } }

    private func open(_ probe: @escaping @Sendable (APIClient) async throws -> StudioSource) {
        ticket += 1
        let mine = ticket
        phase = .probing
        plan = nil
        queuedFor = nil
        let client = client()
        Task {
            do {
                let source = try await probe(client)
                guard mine == ticket else { return }
                start(with: source)
                await loadKeyframes(source, client: client, ticket: mine)
            } catch {
                guard mine == ticket else { return }
                phase = .failed(APIError.from(error))
            }
        }
    }

    func start(with source: StudioSource) {
        grid = TimeGrid(rate: source.frameRate, duration: source.duration ?? 0, origin: source.videoStart ?? 0)
        segments = [TrimSegment(start: 0, end: grid.count)]
        active = 0
        join = false
        keyframes = []
        keyframesLoaded = false
        tracks = Self.tracks(of: source, input: 0)
        extras = []
        audioIndex = 0
        subtitleAction = source.youtubeAutoCaptions ? "clean" : "convert"
        nameTouched = false
        phase = .ready(source)
        operation = source.hasMedia ? .trim : .subtitle
        followName()
    }

    private func loadKeyframes(_ source: StudioSource, client: APIClient, ticket mine: Int) async {
        guard source.hasVideo, let times = try? await client.keyframes(path: source.path), mine == ticket else {
            if mine == ticket { keyframesLoaded = true }
            return
        }
        // Keyframe times count from the first video frame; a millisecond grid (sound, or a
        // variable frame rate) counts from the start of the file.
        let shift = grid.isFrames ? 0 : (source.videoStart ?? 0)
        injectKeyframes(grid.positions(of: times.map { $0 + shift }))
    }

    func injectKeyframes(_ positions: [Int]) {
        keyframes = positions
        keyframesLoaded = true
        if trimMode == .lossless { snapAll() }
    }

    static func tracks(of source: StudioSource, input: Int) -> [Track] {
        source.streams.filter { ["video", "audio", "subtitle"].contains($0.type ?? "") }.map { stream in
            Track(input: input, stream: stream, from: source.name,
                  language: stream.language.flatMap { $0 == "und" ? nil : $0 } ?? "",
                  title: stream.title ?? "", isDefault: stream.default)
        }
    }

    /// The output name follows the operation until Berk types his own.
    private func followName() {
        guard let source, !nameTouched else { return }
        let stem = (source.name as NSString).deletingPathExtension
        suggestedName = "\(stem) \(L("studio.outputSuffix.\(operation.rawValue)"))"
        outputName = suggestedName
    }

    public func allowed(_ op: Operation) -> Bool {
        guard let source else { return false }
        return op == .subtitle ? !source.hasMedia : source.hasMedia
    }

    // ---- the pieces -------------------------------------------------------------------------

    public var current: TrimSegment? { segments.indices.contains(active) ? segments[active] : nil }

    /// Moves the active piece's start; never past its end, on a keyframe in lossless mode.
    public func setStart(_ position: Int) {
        guard var segment = current else { return }
        var start = grid.clamp(position, upper: segment.end - 1)
        if trimMode == .lossless, !keyframes.isEmpty {
            start = nearestKeyframe(start, in: keyframes.filter { $0 < segment.end })
        }
        segment.start = start
        segments[active] = segment
    }

    public func setEnd(_ position: Int) {
        guard var segment = current else { return }
        segment.end = max(segment.start + 1, grid.clamp(position))
        segments[active] = segment
    }

    public func nudgeStart(_ by: Int) {
        guard let segment = current else { return }
        if trimMode == .lossless, !keyframes.isEmpty {
            let next = by < 0 ? keyframe(before: segment.start, in: keyframes) : keyframe(after: segment.start, in: keyframes)
            if let next, next < segment.end { segments[active].start = next }
            return
        }
        setStart(segment.start + by)
    }

    public func nudgeEnd(_ by: Int) {
        guard let segment = current else { return }
        setEnd(segment.end + by)
    }

    public func addSegment() {
        // After the last piece when there is room, else the whole file.
        let last = segments.last?.end ?? 0
        let piece = last < grid.count - 1 ? TrimSegment(start: last, end: grid.count) : TrimSegment(start: 0, end: grid.count)
        segments.append(piece)
        active = segments.count - 1
        if trimMode == .lossless { snapAll() }
    }

    public func removeSegment(at index: Int) {
        guard segments.count > 1, segments.indices.contains(index) else { return }
        segments.remove(at: index)
        active = min(active, segments.count - 1)
    }

    /// A chapter becomes the active piece (or replaces the untouched whole-file piece).
    public func useChapter(_ chapter: StudioChapter) {
        let piece = TrimSegment(start: grid.position(chapter.start), end: max(grid.position(chapter.start) + 1, grid.position(chapter.end)))
        if segments.count == 1, segments[0].start == 0, segments[0].end == grid.count {
            segments = [piece]
            active = 0
        } else {
            segments.append(piece)
            active = segments.count - 1
        }
        if trimMode == .lossless { snapAll() }
    }

    private func snapAll() {
        guard !keyframes.isEmpty else { return }
        for index in segments.indices {
            let segment = segments[index]
            segments[index].start = nearestKeyframe(segment.start, in: keyframes.filter { $0 < segment.end })
        }
    }

    // ---- remux --------------------------------------------------------------------------------

    public func moveTrack(_ index: Int, by offset: Int) {
        let target = index + offset
        guard tracks.indices.contains(index), tracks.indices.contains(target) else { return }
        tracks.swapAt(index, target)
    }

    public func addExtra(path: String) async {
        do {
            let extra = try await client().studioProbe(path: path)
            extras.append(extra)
            tracks += Self.tracks(of: extra, input: extras.count)
        } catch {
            failure = APIError.from(error)
        }
    }

    // ---- the request --------------------------------------------------------------------------

    public var offsetSeconds: Double? {
        let text = offset.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: ".")
        guard text.wholeMatch(of: /-?\d+(\.\d+)?/) != nil else { return nil }
        return Double(text)
    }

    /// The body `/api/studio/plan` and `/api/studio/jobs` receive, or nil when it is not complete.
    public var body: [String: any Sendable]? {
        guard let source, !outputName.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
        let options: [String: any Sendable]
        switch operation {
        case .audio:
            options = [
                "codec": audioCodec,
                "bitrate": Self.lossy.contains(audioCodec) ? bitrate : NSNull(),
                "sample_rate": Int(sampleRate).map { $0 as any Sendable } ?? NSNull(),
                "channels": Int(channels).map { $0 as any Sendable } ?? NSNull(),
                "audio_index": audioIndex,
                "loudnorm": loudnorm,
            ]
        case .trim:
            // Frames when the source has a frame grid (the backend turns them into time with the
            // source's own rate); seconds, to the millisecond, for sound.
            let pieces: [[String: any Sendable]] = segments.map { piece in
                grid.isFrames ? ["start_frame": piece.start, "end_frame": piece.end]
                              : ["start": grid.seconds(piece.start), "end": grid.seconds(piece.end)]
            }
            options = ["mode": trimMode.rawValue, "join": join, "segments": pieces]
        case .remux:
            options = [
                "container": container,
                "tracks": tracks.map { track -> [String: any Sendable] in
                    [
                        "input": track.input, "stream": track.stream.index, "keep": track.keep,
                        "language": track.language.isEmpty ? NSNull() : track.language,
                        "title": track.title.isEmpty ? NSNull() : track.title,
                        "default": track.isDefault,
                    ]
                },
            ]
        case .subtitle:
            guard let offsetSeconds else { return nil }
            options = ["action": subtitleAction, "target": subtitleTarget, "offset": offsetSeconds]
        }
        return [
            "source_path": source.path,
            "op": operation.rawValue,
            "options": options,
            "output_name": outputName.trimmingCharacters(in: .whitespaces),
            "extra_paths": operation == .remux ? extras.map(\.path) : [String](),
        ]
    }

    /// The body as a stable string: what the plan on screen was computed for.
    public var bodyKey: String? {
        guard let body, let data = try? JSONSerialization.data(withJSONObject: body, options: [.sortedKeys]) else { return nil }
        return String(decoding: data, as: UTF8.self)
    }

    public var planIsCurrent: Bool { plan != nil && planFor != nil && planFor == bodyKey }
    public var queued: Bool { queuedFor != nil && queuedFor == bodyKey }
    public var canRun: Bool { planIsCurrent && plan?.blocking == false && !submitting && !queued }

    public func refreshPlan() async {
        guard let body, let key = bodyKey else {
            plan = nil
            planFor = nil
            return
        }
        do {
            let next = try await client().studioPlan(body)
            guard !Task.isCancelled, key == bodyKey else { return }
            plan = next
            planFor = key
            failure = nil
        } catch {
            guard !Task.isCancelled else { return }
            failure = APIError.from(error)
        }
    }

    public func run() async {
        guard canRun, let body, let key = bodyKey else { return }
        submitting = true
        defer { submitting = false }
        do {
            _ = try await client().studioJob(body)
            queuedFor = key
        } catch {
            failure = APIError.from(error)
        }
    }
}
