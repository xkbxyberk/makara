import Foundation

/// This Mac and the local network: never something to inspect on someone else's say-so.
/// Inspecting makes the backend fetch the URL; a web page could otherwise aim that at a router,
/// a NAS or the app's own API (through the URL scheme, a crafted link in the menu, a tab).
public enum LocalHost {
    public static func isLocal(_ rawHost: String) -> Bool {
        let host = rawHost.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        if host.isEmpty || host == "localhost" || host.hasSuffix(".localhost") || host.hasSuffix(".local")
            || (!host.contains(".") && !host.contains(":")) {
            return true
        }
        if host.contains(":") {  // IPv6: loopback, unspecified, link-local, unique-local, v4-mapped
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

    /// A public http(s) page, or nil.
    public static func publicWebPage(_ url: URL) -> URL? {
        guard ["http", "https"].contains(url.scheme?.lowercased() ?? ""), let host = url.host(), !isLocal(host) else { return nil }
        return url
    }
}
