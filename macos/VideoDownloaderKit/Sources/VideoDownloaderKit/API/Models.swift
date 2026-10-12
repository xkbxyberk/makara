import Foundation

/// The backend's JSON, decoded with snake_case keys. Only the fields the native app reads are
/// declared; the contract samples in `tests/fixtures/api/` keep these honest (see ContractTests).
public struct Health: Decodable, Sendable, Equatable {
    public let ok: Bool
    public let fixtureMode: Bool
}

public struct AppSettings: Decodable, Sendable, Equatable {
    public let downloadDir: String
    public let filenameTemplate: String
    public let concurrency: Int
    public let defaultMode: String
    public let clipboardWatch: Bool
    public let notifications: Bool
}

public enum JobStatus: String, Decodable, Sendable {
    case queued, running, done, failed, cancelled
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
}
