import Foundation

/// Something handed to the app from outside: `videodownloader://inspect?url=…`, a web link
/// dropped on the Dock icon or the window, or a `.webloc` file.
///
/// Inspecting starts without a click (the backend contacts the site), so only public http(s)
/// pages qualify: never another scheme, and never this Mac or the local network -- a web page
/// could otherwise use the URL scheme to make the app probe a router or the app's own API.
public enum IncomingURL: Equatable, Sendable {
    case inspect(URL)
    case show(Route?)

    public static let scheme = "videodownloader"

    public static func parse(_ url: URL, readFile: (URL) -> Data? = { try? Data(contentsOf: $0) }) -> IncomingURL? {
        switch url.scheme?.lowercased() {
        case "http", "https":
            return webPage(url).map(IncomingURL.inspect)
        case scheme:
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

    /// A public http(s) page, or nil.
    static func webPage(_ url: URL) -> URL? {
        guard ["http", "https"].contains(url.scheme?.lowercased() ?? ""),
              let host = url.host()?.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "[]")),
              !host.isEmpty, !isLocal(host) else { return nil }
        return url
    }

    static func isLocal(_ host: String) -> Bool {
        if host == "localhost" || host.hasSuffix(".localhost") || host.hasSuffix(".local") || !host.contains(".") && !host.contains(":") {
            return true
        }
        if host.contains(":") {  // IPv6: loopback, unspecified, link-local, unique-local
            return host == "::1" || host == "::" || host.hasPrefix("fe80:") || host.hasPrefix("fc") || host.hasPrefix("fd")
                || host.hasPrefix("::ffff:")
        }
        let parts = host.split(separator: ".").compactMap { Int($0) }
        guard parts.count == 4, parts.allSatisfy({ (0...255).contains($0) }) else { return false }
        switch (parts[0], parts[1]) {
        case (127, _), (10, _), (0, _), (169, 254), (192, 168): return true
        case (172, let b) where (16...31).contains(b): return true
        case (100, let b) where (64...127).contains(b): return true  // carrier-grade NAT
        default: return false
        }
    }
}
