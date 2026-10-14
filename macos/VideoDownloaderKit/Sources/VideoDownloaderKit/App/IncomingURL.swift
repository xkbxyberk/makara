import Foundation
import VideoDownloaderRelay

/// Something handed to the app from outside: `makara://inspect?url=…`, a web link
/// dropped on the Dock icon or the window, or a `.webloc` file.
///
/// Inspecting starts without a click (the backend contacts the site), so only public http(s)
/// pages qualify: never another scheme, and never this Mac or the local network -- a web page
/// could otherwise use the URL scheme to make the app probe a router or the app's own API.
public enum IncomingURL: Equatable, Sendable {
    case inspect(URL)
    case show(Route?)

    /// The release's scheme and the development build's (each registers only its own).
    public static let schemes: Set<String> = ["makara", "makara-dev"]

    public static func parse(_ url: URL, readFile: (URL) -> Data? = { try? Data(contentsOf: $0) }) -> IncomingURL? {
        switch url.scheme?.lowercased() {
        case "http", "https":
            return webPage(url).map(IncomingURL.inspect)
        case let scheme? where schemes.contains(scheme):
            let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
            switch url.host()?.lowercased() {
            case "inspect":
                return items.first(where: { $0.name == "url" })?.value
                    .flatMap(URL.init(string:)).flatMap(webPage).map(IncomingURL.inspect)
            case "show", nil:
                return .show(items.first(where: { $0.name == "route" })?.value.flatMap(Route.init(rawValue:)))
            default:
                return nil
            }
        case "file":
            // A .webloc holds a link; only a web page counts (no nested file:, no recursion).
            guard url.pathExtension.lowercased() == "webloc", let data = readFile(url),
                  let plist = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any],
                  let raw = plist["URL"] as? String, let target = URL(string: raw) else { return nil }
            return webPage(target).map(IncomingURL.inspect)
        default:
            return nil
        }
    }

    /// A public http(s) page, or nil (one rule for the app and the extension: LocalHost).
    static func webPage(_ url: URL) -> URL? {
        LocalHost.publicWebPage(url)
    }
}
