import Foundation

/// `/api/library`: the catalogue of finished downloads and Stüdyo outputs.
public struct LibraryTrack: Decodable, Sendable, Equatable {
    public let codec: String?
    public let language: String?
    public let height: Int?
}

public struct LibraryFile: Decodable, Sendable, Equatable {
    public let path: String
    public let size: Double?
    public let role: String
}

public struct LibraryItem: Decodable, Sendable, Equatable, Identifiable {
    public struct Tracks: Decodable, Sendable, Equatable {
        public let video: [LibraryTrack]
        public let audio: [LibraryTrack]
        public let subtitle: [LibraryTrack]
    }

    public let id: String
    public let title: String?
    public let sourceUrl: String?
    public let site: String?
    public let channel: String?
    public let uploadDate: String?
    public let mode: String?
    public let kind: String
    /// ok, missing (the file is not where it was recorded) or trashed.
    public let status: String
    public let primaryPath: String
    public let size: Double?
    public let duration: Double?
    public let files: [LibraryFile]
    public let tracks: Tracks
    public let thumbnail: String?
    public let addedAt: Double

    public var isMissing: Bool { status == "missing" }
}

public struct LibraryPage: Decodable, Sendable, Equatable {
    public struct Facets: Decodable, Sendable, Equatable {
        public let sites: [String]
        public let count: Int
        public let totalSize: Double
        public let missing: Int
    }

    public let items: [LibraryItem]
    public let facets: Facets
}

public struct ScanResult: Decodable, Sendable, Equatable {
    public let checked: Int
    public let missing: Int
    public let repaired: Int
    public let restored: Int
}

/// What the list asks for; empty fields are left out of the request.
public struct LibraryQuery: Sendable, Equatable, Hashable {
    public var search = ""
    public var site = ""
    public var kind = ""
    public var status = ""
    public var sort = "added"

    public init() {}

    public var isFiltered: Bool { self != LibraryQuery() }

    var items: [URLQueryItem] {
        [("search", search), ("site", site), ("kind", kind), ("status", status), ("sort", sort)]
            .filter { !$0.1.isEmpty }.map { URLQueryItem(name: $0.0, value: $0.1) }
    }
}
