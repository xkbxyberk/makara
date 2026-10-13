import Foundation

/// What the Safari extension may ask of the app, and nothing more.
///
/// The extension's JavaScript never talks to the backend itself: it sends a message, and the
/// sandboxed native half turns it into one of a handful of allowed requests to 127.0.0.1. A
/// bug in the extension (or a page that somehow reached it) therefore cannot reach the library,
/// the file pickers, the Trash or the yt-dlp updater -- only inspecting and queuing downloads.
public enum Relay {
    /// The app's backend. The extension cannot know a test port; tests drive the relay directly.
    public static let defaultPort = 8787
    static let maxBody = 64 * 1024

    /// (method, path) pairs that may be relayed, and the query keys each may carry.
    static let allowed: [String: Set<String>] = [
        "GET api/health": [],
        "GET api/supports": ["url"],
        "GET api/extension": [],
        "GET api/jobs": [],
        "POST api/inspect": [],
        "POST api/quick": [],
    ]

    public enum Action: Equatable {
        case http(URLRequest)
        /// Open a `videodownloader://` link: brings the app forward (or starts it).
        case open(URL)
    }

    public enum Refusal: String, Error {
        case notAllowed = "RELAY_NOT_ALLOWED"
        case badBody = "RELAY_BAD_BODY"
        /// An inspect or download of this Mac or the local network (see LocalHost).
        case localAddress = "RELAY_LOCAL_ADDRESS"
    }

    public static func action(for message: [String: Any], port: Int = defaultPort) -> Result<Action, Refusal> {
        switch message["type"] as? String {
        case "open":
            guard let raw = message["url"] as? String, let url = URL(string: raw),
                  url.scheme == "videodownloader", ["inspect", "show"].contains(url.host() ?? "") else {
                return .failure(.notAllowed)
            }
            return .success(.open(url))
        case "api":
            return httpAction(message, port: port)
        default:
            return .failure(.notAllowed)
        }
    }

    private static func httpAction(_ message: [String: Any], port: Int) -> Result<Action, Refusal> {
        let method = (message["method"] as? String ?? "GET").uppercased()
        guard let path = message["path"] as? String, let keys = allowed["\(method) \(path)"] else {
            return .failure(.notAllowed)
        }
        let query = message["query"] as? [String: String] ?? [:]
        guard Set(query.keys).isSubset(of: keys) else { return .failure(.notAllowed) }
        var components = URLComponents()
        components.scheme = "http"
        components.host = "127.0.0.1"
        components.port = port
        components.path = "/" + path
        // Encoded by hand: URLComponents leaves "+" alone, which the server reads as a space.
        if !query.isEmpty {
            components.percentEncodedQuery = query.sorted { $0.key < $1.key }
                .map { "\(encode($0.key))=\(encode($0.value))" }.joined(separator: "&")
        }
        guard let url = components.url else { return .failure(.notAllowed) }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = method == "POST" ? 240 : 5  // an inspect can take a while
        if method == "POST" {
            guard let body = message["body"] as? [String: Any], JSONSerialization.isValidJSONObject(body),
                  let data = try? JSONSerialization.data(withJSONObject: body), data.count <= maxBody else {
                return .failure(.badBody)
            }
            // The extension may make the app fetch public pages only, whoever built the link.
            if let raw = body["url"] {
                guard let text = raw as? String, let target = URL(string: text), LocalHost.publicWebPage(target) != nil else {
                    return .failure(.localAddress)
                }
            }
            request.httpBody = data
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return .success(.http(request))
    }

    private static let queryValue: CharacterSet = {
        var allowed = CharacterSet.urlQueryAllowed
        allowed.remove(charactersIn: "+&=?#")
        return allowed
    }()

    private static func encode(_ text: String) -> String {
        text.addingPercentEncoding(withAllowedCharacters: queryValue) ?? ""
    }

    /// The answer the extension gets: `ok`, the HTTP status, the decoded JSON; `offline` when
    /// nothing answered (the app is not running).
    public static func reply(data: Data?, response: URLResponse?, error: Error?) -> [String: Any] {
        if error != nil || response == nil {
            return ["ok": false, "offline": true]
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let json = data.flatMap { try? JSONSerialization.jsonObject(with: $0) } ?? NSNull()
        return ["ok": (200..<300).contains(status), "status": status, "json": json]
    }
}
