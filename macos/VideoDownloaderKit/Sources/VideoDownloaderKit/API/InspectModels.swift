import Foundation

/// `/api/inspect` (the output of `normalize.py`, plus the quick choices of `offers.py`) and
/// `/api/plan`, as the native İncele screen reads them. Decoded with `JSON.decoder` (snake
/// case), except `Plan`, whose notice params are a free dictionary (see `JSON.plain`).
public enum InspectResult: Decodable, Sendable, Equatable {
    case video(VideoModel)
    case playlist(PlaylistModel)

    private enum Keys: String, CodingKey { case kind }

    public init(from decoder: Decoder) throws {
        let kind = try decoder.container(keyedBy: Keys.self).decode(String.self, forKey: .kind)
        self = kind == "playlist" ? .playlist(try PlaylistModel(from: decoder)) : .video(try VideoModel(from: decoder))
    }

    public var sourceUrl: String {
        switch self {
        case .video(let model): model.sourceUrl
        case .playlist(let model): model.sourceUrl
        }
    }
}

public enum SizeKind: String, Decodable, Sendable {
    case exact, approx, estimated, partial, unknown

    public init(from decoder: Decoder) throws {
        self = SizeKind(rawValue: try decoder.singleValueContainer().decode(String.self)) ?? .unknown
    }

    /// The marker that says how much to trust a size (as the web page's `sizePrefix`).
    public var prefix: String {
        switch self {
        case .approx: "≈"
        case .estimated: "~"
        case .partial: "≥"
        default: ""
        }
    }
}

public struct VideoFormat: Decodable, Sendable, Equatable, Identifiable {
    public var id: String { formatId }
    public let formatId: String
    public let ext: String?
    public let isManifest: Bool
    public let filesize: Double?
    public let filesizeKind: SizeKind
    public let filesizeUnreliable: Bool
    public let tbr: Double?
    public let drm: String
    public let aiUpscaled: Bool
    public let drc: Bool
    public let width: Int?
    public let height: Int?
    public let resolution: String?
    public let fps: Double?
    public let vcodecLabel: String?
    public let dynamicRange: String?
    /// true: carries sound; false: silent; nil: unknown.
    public let hasAudio: Bool?
    public let acodecLabel: String?
}

public struct AudioFormat: Decodable, Sendable, Equatable, Identifiable {
    public var id: String { formatId }
    public let formatId: String
    public let ext: String?
    public let filesize: Double?
    public let filesizeKind: SizeKind
    public let filesizeUnreliable: Bool
    public let tbr: Double?
    public let drm: String
    public let formatNote: String?
    public let aiUpscaled: Bool
    public let drc: Bool
    public let acodecLabel: String?
    public let abr: Double?
    public let asr: Double?
    public let channels: Int?
}

public struct AudioLanguageGroup: Decodable, Sendable, Equatable, Identifiable {
    public var id: String { language ?? "und" }
    public let language: String?
    public let role: String
    public let tracks: [AudioFormat]
}

public struct SubtitleTrack: Decodable, Sendable, Equatable, Identifiable {
    public var id: String { key }
    public let key: String
    public let language: String
    public let name: String?
    public let exts: [String]
    public let sourceLanguage: String?
    public var isOriginalTrack: Bool? = nil
    public var shadowedByManual: Bool? = nil
}

public struct Subtitles: Decodable, Sendable, Equatable {
    public let manual: [SubtitleTrack]
    public let auto: [SubtitleTrack]
    public let autoTranslated: [SubtitleTrack]
    public let hasLiveChat: Bool
}

public struct Chapter: Decodable, Sendable, Equatable {
    public let startTime: Double?
    public let title: String?
}

public struct HeatmapPoint: Decodable, Sendable, Equatable {
    public let value: Double?
}

public struct Thumbnail: Decodable, Sendable, Equatable {
    public let id: String?
    public let url: String
    public let width: Int?
    public let height: Int?
}

public struct MediaMeta: Decodable, Sendable, Equatable {
    public let title: String?
    public var description: String? = nil
    public let extractor: String?
    public let channel: String?
    public var uploadDate: String? = nil
    public var duration: Double? = nil
    public var viewCount: Double? = nil
    public var thumbnail: String? = nil
}

public struct InspectCommands: Decodable, Sendable, Equatable {
    public let inspect: String
    public let suggested: String
}

/// The tracks of one output: what the panel edits and `/api/plan` and `/api/jobs` receive.
public struct TrackSelection: Codable, Sendable, Equatable, Hashable {
    public var videoFormatId: String?
    public var audioFormatIds: [String]
    public var subtitleKeys: [String]
}

public enum Mode: String, Codable, Sendable, CaseIterable, Identifiable {
    case mkv, compatMp4 = "compat_mp4", separate, audio
    public var id: String { rawValue }
}

/// `defaults`: the starting tracks for each output (original audio, manual TR/EN subtitles).
public struct ModeDefaults: Decodable, Sendable, Equatable {
    public let mkv: TrackSelection
    public let compatMp4: TrackSelection
    public let separate: TrackSelection
    public let audio: TrackSelection

    public subscript(mode: Mode) -> TrackSelection {
        switch mode {
        case .mkv: mkv
        case .compatMp4: compatMp4
        case .separate: separate
        case .audio: audio
        }
    }
}

public struct OfferSize: Decodable, Sendable, Equatable {
    public let bytes: Double?
    public let kind: SizeKind
    public let unreliable: Bool
}

/// The remembered shape of a quick choice ("1080p, MKV"), carried to the next video of a site.
public struct QuickRule: Codable, Sendable, Equatable {
    public var kind: String
    public var height: Int?
    public var fps: Double?
    public var hdr: Bool?
    public var output: String?
    public var format: String?

    public init(kind: String, height: Int? = nil, fps: Double? = nil, hdr: Bool? = nil,
                output: String? = nil, format: String? = nil) {
        self.kind = kind
        self.height = height
        self.fps = fps
        self.hdr = hdr
        self.output = output
        self.format = format
    }

    /// Only a well-formed rule is sent (as `quickRule.ts valid`).
    public var isValid: Bool {
        func ok(_ value: Double?, _ max: Double) -> Bool { value.map { $0.isFinite && $0 > 0 && $0 <= max } ?? true }
        if kind == "audio" { return ["opus", "m4a", "mp3"].contains(format ?? "") }
        return kind == "video" && ok(height.map(Double.init), 10_000) && ok(fps, 1000)
            && (output == nil || output == "mkv" || output == "compat_mp4")
    }
}

public struct OfferSelection: Decodable, Sendable, Equatable {
    public let videoFormatId: String?
    public let audioFormatIds: [String]
    public let subtitleKeys: [String]
    public let audioQuality: String?
}

public struct VideoOutput: Decodable, Sendable, Equatable {
    public let selection: OfferSelection
    public let videoFormatId: String
    public let vcodecLabel: String?
    public let size: OfferSize
    /// The heaviest step of any track: what the row's badge says.
    public let step: String
}

public struct VideoOffer: Decodable, Sendable, Equatable, Identifiable {
    public struct Outputs: Decodable, Sendable, Equatable {
        public let mkv: VideoOutput
        public let compatMp4: VideoOutput
    }

    public let id: String
    public let height: Int?
    public let fps: Double?
    public let dynamicRange: String?
    public let aiUpscaled: Bool
    public let outputs: Outputs
    public let rule: QuickRule

    /// MKV for every mode but the compatible MP4 (as the web page's QuickChoices).
    public func output(for mode: Mode) -> VideoOutput { mode == .compatMp4 ? outputs.compatMp4 : outputs.mkv }
}

public struct AudioOffer: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let format: String
    public let formatId: String
    public let sourceCodecLabel: String?
    public let abr: Double?
    public let step: String
    public let size: OfferSize
    public let rule: QuickRule
    public let selection: OfferSelection
}

public struct Offers: Decodable, Sendable, Equatable {
    public struct Preselected: Decodable, Sendable, Equatable {
        public let offerId: String
        public let output: String?
    }

    public let video: [VideoOffer]
    public let audio: [AudioOffer]
    public let preselected: Preselected?
}

public struct VideoModel: Decodable, Sendable, Equatable {
    public let inspectId: String
    public let defaults: ModeDefaults
    public let offers: Offers
    public let media: MediaMeta
    public let videoFormats: [VideoFormat]
    public let muxedFormats: [VideoFormat]
    public let audioLanguages: [AudioLanguageGroup]
    public let subtitles: Subtitles
    public let chapters: [Chapter]
    public let heatmap: [HeatmapPoint]
    public let thumbnails: [Thumbnail]
    public let warnings: [String]
    public let sourceUrl: String
    public let commands: InspectCommands
}

public struct PlaylistEntry: Decodable, Sendable, Equatable {
    public let id: String?
    public let title: String?
    public let url: String?
    public let duration: Double?
}

public struct PlaylistModel: Decodable, Sendable, Equatable {
    public struct Media: Decodable, Sendable, Equatable { public let title: String? }
    public let media: Media
    public let entries: [PlaylistEntry]
    public let entryCount: Int
    public let warnings: [String]
    public let sourceUrl: String
}

/// What the panel sends to `/api/plan` and `/api/jobs`.
public struct Selection: Encodable, Sendable, Equatable, Hashable {
    public struct Extras: Codable, Sendable, Equatable, Hashable {
        public var thumbnail = true
        public var thumbnailFile = false
        public var description = false
        public var infoJson = false
        public init() {}
    }

    public var inspectId: String
    public var mode: Mode
    public var videoFormatId: String?
    public var audioFormatIds: [String]
    public var subtitleKeys: [String]
    public var audioCodec: String?
    public var audioQuality: String?
    public var filenameTemplate: String?
    public var extras: Extras

    private enum CodingKeys: String, CodingKey {
        case inspectId, mode, videoFormatId, audioFormatIds, subtitleKeys, audioCodec, audioQuality,
             filenameTemplate, extras
    }

    /// Nil values are sent as JSON null, as the web page does (the backend expects every key).
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(inspectId, forKey: .inspectId)
        try c.encode(mode, forKey: .mode)
        try c.encode(videoFormatId, forKey: .videoFormatId)
        try c.encode(audioFormatIds, forKey: .audioFormatIds)
        try c.encode(subtitleKeys, forKey: .subtitleKeys)
        try c.encode(audioCodec, forKey: .audioCodec)
        try c.encode(audioQuality, forKey: .audioQuality)
        try c.encode(filenameTemplate, forKey: .filenameTemplate)
        try c.encode(extras, forKey: .extras)
    }
}

/// `/api/plan`: what a selection will produce, before anything is downloaded.
public struct Plan: Decodable, Sendable, Equatable {
    public struct Size: Decodable, Sendable, Equatable {
        public let bytes: Double?
        public let kind: SizeKind
        public let unreliable: Bool
    }

    public struct Notice: Decodable, Sendable, Equatable {
        public let code: String
        public let level: String
        public let params: [String: JSONValue]
    }

    public let size: Size
    public let notices: [Notice]
    public let blocking: Bool
    public let filename: String?
    public let filenameError: String?
    public let downloadDir: String
    public let command: String

    private enum CodingKeys: String, CodingKey {
        case size, notices, blocking, filename, command
        case filenameError = "filename_error"
        case downloadDir = "download_dir"
    }
}
