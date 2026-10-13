import Foundation

/// The backend's JSON, decoded with snake_case keys. Only the fields the native app reads are
/// declared; the contract samples in `tests/fixtures/api/` keep these honest (see ContractTests).
public struct Health: Decodable, Sendable, Equatable {
    public let ok: Bool
    public let fixtureMode: Bool
}

public struct AppSettings: Codable, Sendable, Equatable {
    public var downloadDir: String
    public var filenameTemplate: String
    public var concurrency: Int
    public var defaultMode: String
    public var clipboardWatch: Bool
    public var notifications: Bool
    public var safariLogin: Bool = true
    /// Several connections per download (aria2c, parallel fragments), and a cap in bytes/s (0: none).
    public var accelerate: Bool = true
    public var connections: Int = 8
    public var rateLimit: Int = 0
    /// The Safari extension: "page" (a card on the page offers the video) or "icon" (only its icon).
    public var extensionOffer: String = "page"
    /// Read-only: the app's built-in template, for "Varsayılana dön".
    public var defaultFilenameTemplate: String? = nil

    private enum CodingKeys: String, CodingKey {
        case downloadDir, filenameTemplate, concurrency, defaultMode, clipboardWatch, notifications, safariLogin
        case extensionOffer, accelerate, connections, rateLimit
        case defaultFilenameTemplate
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        downloadDir = try c.decode(String.self, forKey: .downloadDir)
        filenameTemplate = try c.decode(String.self, forKey: .filenameTemplate)
        concurrency = try c.decode(Int.self, forKey: .concurrency)
        defaultMode = try c.decode(String.self, forKey: .defaultMode)
        clipboardWatch = try c.decode(Bool.self, forKey: .clipboardWatch)
        notifications = try c.decode(Bool.self, forKey: .notifications)
        // Newer settings: an older answer without them keeps the defaults.
        safariLogin = try c.decodeIfPresent(Bool.self, forKey: .safariLogin) ?? true
        extensionOffer = try c.decodeIfPresent(String.self, forKey: .extensionOffer) ?? "page"
        accelerate = try c.decodeIfPresent(Bool.self, forKey: .accelerate) ?? true
        connections = try c.decodeIfPresent(Int.self, forKey: .connections) ?? 8
        rateLimit = try c.decodeIfPresent(Int.self, forKey: .rateLimit) ?? 0
        defaultFilenameTemplate = try c.decodeIfPresent(String.self, forKey: .defaultFilenameTemplate)
    }

    /// What `PUT /api/settings` takes (everything but the read-only template).
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(downloadDir, forKey: .downloadDir)
        try c.encode(filenameTemplate, forKey: .filenameTemplate)
        try c.encode(concurrency, forKey: .concurrency)
        try c.encode(defaultMode, forKey: .defaultMode)
        try c.encode(clipboardWatch, forKey: .clipboardWatch)
        try c.encode(notifications, forKey: .notifications)
        try c.encode(safariLogin, forKey: .safariLogin)
        try c.encode(extensionOffer, forKey: .extensionOffer)
        try c.encode(accelerate, forKey: .accelerate)
        try c.encode(connections, forKey: .connections)
        try c.encode(rateLimit, forKey: .rateLimit)
    }
}

public enum JobStatus: String, Decodable, Sendable {
    case queued, running, paused, done, failed, cancelled
    case unknown

    public init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = JobStatus(rawValue: raw) ?? .unknown
    }

    public var isActive: Bool { self == .queued || self == .running }
}

public struct Job: Decodable, Sendable, Identifiable, Equatable {
    public let id: String
    public let kind: String
    public let status: JobStatus
    public let stage: String?
    public let title: String?
    public let sourceUrl: String?
    public let mode: String?
    public let progress: Double?
    public let outputFiles: [String]
    public let errorCode: String?
    public var errorRaw: String? = nil
    /// Bytes per second and seconds left, while downloading.
    public var speed: Double? = nil
    public var eta: Double? = nil
    /// "3/12" in a playlist.
    public var itemIndex: Int? = nil
    public var itemCount: Int? = nil
    public var warnings: [JobWarning]? = nil
    public var createdAt: Double? = nil
    /// The download used Berk's Safari session (an age-restricted video).
    public var usedSession: Bool? = nil
    /// Automatic retries so far, and when the waiting one starts (P6d, stage "waiting_retry").
    public var attempts: Int? = nil
    public var retryAt: Double? = nil

    /// Downloading with a percentage to show; the other running stages only say they run.
    public var isIndeterminate: Bool {
        status == .running && (Self.indeterminateStages.contains(stage ?? "") || (progress ?? 0) <= 0)
    }

    static let indeterminateStages: Set<String> = ["starting", "preparing", "postprocessing", "cancelling"]
}

public struct JobWarning: Decodable, Sendable, Equatable, Hashable {
    public let code: String
    public var key: String? = nil
}

/// `/api/doctor`. Decoded with `JSON.plain`: the values are dictionaries whose keys
/// (`ffmpeg_path`, `videotoolbox_h264`) must stay as the backend wrote them.
public struct DoctorReport: Decodable, Sendable, Equatable {
    public let status: CheckStatus
    public let checks: [DoctorCheck]
}

public enum CheckStatus: String, Decodable, Sendable {
    case ok, warn, error
}

public struct DoctorCheck: Decodable, Sendable, Equatable, Identifiable {
    public struct Fix: Decodable, Sendable, Equatable {
        public let kind: String
        public let command: String
    }

    public let id: String
    public let status: CheckStatus
    public let values: [String: JSONValue]
    public let fix: Fix
}

public struct UpdateResult: Decodable, Sendable, Equatable {
    public struct Version: Decodable, Sendable, Equatable { public let version: String }
    public let before: Version
    public let after: Version
    public let changed: Bool
}

/// Any JSON value, for the doctor's free-form `values`.
public enum JSONValue: Decodable, Sendable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case array([JSONValue])
    case object([String: JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { self = .null }
        else if let value = try? container.decode(Bool.self) { self = .bool(value) }
        else if let value = try? container.decode(Double.self) { self = .number(value) }
        else if let value = try? container.decode(String.self) { self = .string(value) }
        else if let value = try? container.decode([JSONValue].self) { self = .array(value) }
        else { self = .object(try container.decode([String: JSONValue].self)) }
    }

    public var string: String? {
        if case .string(let value) = self { return value }
        return nil
    }

    /// How the web page prints a value: text as is, nothing as "–".
    public var display: String {
        switch self {
        case .string(let value): value.isEmpty ? "" : value
        case .number(let value): value == value.rounded() && abs(value) < 1e15 ? String(Int(value)) : String(value)
        case .bool(let value): String(value)
        case .null: "–"
        case .array(let items): items.map(\.display).joined(separator: ", ")
        case .object: ""
        }
    }
}

public struct Supports: Decodable, Sendable, Equatable {
    public let supported: Bool
    public let extractor: String?
    public let working: Bool?
    public let kind: String?
}

/// `{"error": {"code", "raw"}}`: a stable code, never prose (the UI owns the wording).
public struct APIErrorBody: Decodable, Sendable {
    public struct Inner: Decodable, Sendable {
        public let code: String
        public let raw: String?
    }

    public let error: Inner
}

public enum JSON {
    public static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    /// Keys exactly as sent: `convertFromSnakeCase` rewrites dictionary keys too.
    public static let plain = JSONDecoder()

    public static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()
}
