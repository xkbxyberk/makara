import Foundation

/// `/api/studio/probe`: what a source file holds. Decoded with `JSON.decoder`.
public struct StudioStream: Decodable, Sendable, Equatable, Identifiable {
    public var id: Int { index }
    public let index: Int
    public let type: String?
    public let codec: String?
    public let language: String?
    public let title: String?
    public let `default`: Bool
    public let attachedPic: Bool
    public let width: Int?
    public let height: Int?
    public let channels: Int?
}

public struct FrameRate: Decodable, Sendable, Equatable, Hashable {
    public let num: Int
    public let den: Int

    public init(num: Int, den: Int) {
        self.num = num
        self.den = den
    }

    public var perSecond: Double { Double(num) / Double(den) }
    /// The length of one frame.
    public var seconds: Double { Double(den) / Double(num) }
}

public struct StudioChapter: Decodable, Sendable, Equatable {
    public let start: Double
    public let end: Double
    public let title: String?
}

public struct StudioSource: Decodable, Sendable, Equatable {
    public let path: String
    public let name: String
    public let ext: String
    public let size: Double?
    public let duration: Double?
    public let streams: [StudioStream]
    public let chapters: [StudioChapter]
    public let youtubeAutoCaptions: Bool
    /// The video's frame grid; nil for sound-only files (and pictures).
    public var frameRate: FrameRate? = nil
    public var variableFrameRate: Bool? = nil
    /// Where frame 0 is, in seconds from the start of the file (the picture can start after the
    /// sound; an MPEG-TS starts far from 0). The player's clock counts from the file's start.
    public var videoStart: Double? = nil

    public var hasVideo: Bool { streams.contains { $0.type == "video" && !$0.attachedPic } }
    public var hasMedia: Bool { streams.contains { ($0.type == "video" && !$0.attachedPic) || $0.type == "audio" } }
    public var audioStreams: [StudioStream] { streams.filter { $0.type == "audio" } }
}

/// `/api/studio/plan`: exactly what will run. Decoded with `JSON.plain` (free notice params).
public struct StudioPlan: Decodable, Sendable, Equatable {
    public struct Step: Decodable, Sendable, Equatable {
        public let kind: String
        public let action: String
        public let command: String
    }

    public let steps: [Step]
    public let notices: [Plan.Notice]
    public let blocking: Bool
    public let outputs: [String]
}

/// `/api/studio/preview`: the copy of a source macOS's player can play (see preview.py).
public struct PreviewStatus: Decodable, Sendable, Equatable {
    /// none, running, ready or failed.
    public let state: String
    public let path: String?
    public let progress: Double
    public let error: String?
}

struct Keyframes: Decodable { let times: [Double] }
