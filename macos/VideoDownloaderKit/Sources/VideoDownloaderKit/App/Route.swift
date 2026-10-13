import Foundation

/// The sidebar's screens. The raw values are the web app's route ids (see App.tsx `ROUTES`);
/// Settings is not here: it is its own window (⌘,), as on every Mac app.
public enum Route: String, CaseIterable, Identifiable, Sendable {
    case inspect, download, library, studio, doctor

    public var id: String { rawValue }

    public static let media: [Route] = [.inspect, .download, .library, .studio]

    public static let app: [Route] = [.doctor]

    public var title: String {
        switch self {
        case .inspect: L("nav.inspect")
        case .download: L("nav.download")
        case .library: L("nav.library")
        case .studio: L("nav.studio")
        case .doctor: L("nav.doctor")
        }
    }

    public var symbol: String {
        switch self {
        case .inspect: "magnifyingglass"
        case .download: "arrow.down.circle"
        case .library: "books.vertical"
        case .studio: "scissors"
        case .doctor: "stethoscope"
        }
    }

    /// ⌘1 … ⌘5, in sidebar order.
    public var shortcut: Character {
        Character(String((Route.allCases.firstIndex(of: self) ?? 0) + 1))
    }
}
