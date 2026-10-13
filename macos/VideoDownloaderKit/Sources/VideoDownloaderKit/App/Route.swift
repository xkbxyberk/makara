import Foundation

/// The sidebar's screens. The raw values are the web app's route ids (see App.tsx `ROUTES`);
/// Settings is not here: it is its own window (⌘,), as on every Mac app.
public enum Route: String, CaseIterable, Identifiable, Sendable {
    case inspect, download, library, studio, doctor
    /// Kütüphane's shelves (Berk, 2026-10-14): the same screen, one kind of item each.
    case videos, music, edits

    public var id: String { rawValue }

    public static let media: [Route] = [.inspect, .download, .library, .studio]

    public static let app: [Route] = [.doctor]

    public static let shelves: [Route] = [.videos, .music, .edits]

    /// The library's `category` for this route: "" for the whole library, nil off the library.
    public var libraryCategory: String? {
        switch self {
        case .library: ""
        case .videos: "videos"
        case .music: "music"
        case .edits: "studio"
        default: nil
        }
    }

    public var title: String {
        switch self {
        case .inspect: L("nav.inspect")
        case .download: L("nav.download")
        case .library: L("nav.library")
        case .studio: L("nav.studio")
        case .doctor: L("nav.doctor")
        case .videos: L("nav.videos")
        case .music: L("nav.music")
        case .edits: L("nav.edits")
        }
    }

    public var symbol: String {
        switch self {
        case .inspect: "magnifyingglass"
        case .download: "arrow.down.circle"
        case .library: "books.vertical"
        case .studio: "scissors"
        case .doctor: "stethoscope"
        case .videos: "film"
        case .music: "music.note"
        case .edits: "wand.and.stars"
        }
    }

    /// ⌘1 … ⌘5, in sidebar order.
    public var shortcut: Character {
        Character(String((Route.allCases.firstIndex(of: self) ?? 0) + 1))
    }
}
