import Foundation

/// What `/api/events` sends. Unknown event types are kept, not dropped, so a newer backend
/// never breaks an older app.
public enum ServerEvent: Sendable, Equatable {
    case snapshot([Job])
    case job(Job)
    case removed(String)
    case library
    case clipboard(String)
    case other(String)

    struct JobPayload: Decodable { let job: Job }
    struct RemovedPayload: Decodable { let id: String }
    struct ClipboardPayload: Decodable { let url: String }

    static func decode(name: String, data: String) -> ServerEvent? {
        let bytes = Data(data.utf8)
        let d = JSON.decoder
        switch name {
        case "snapshot": return (try? d.decode([Job].self, from: bytes)).map(ServerEvent.snapshot)
        case "job": return (try? d.decode(JobPayload.self, from: bytes)).map { .job($0.job) }
        case "removed": return (try? d.decode(RemovedPayload.self, from: bytes)).map { .removed($0.id) }
        case "library", "library_error": return .library
        case "clipboard": return (try? d.decode(ClipboardPayload.self, from: bytes)).map { .clipboard($0.url) }
        default: return .other(name)
        }
    }
}

/// The text/event-stream format, line by line (WHATWG "server-sent events"): `event:` names
/// the next dispatch, `data:` lines accumulate, a blank line dispatches, `:` is a comment.
public struct SSEParser: Sendable {
    private var event = ""
    private var data: [String] = []

    public init() {}

    public mutating func feed(line raw: String) -> (name: String, data: String)? {
        let line = raw.hasSuffix("\r") ? String(raw.dropLast()) : raw
        if line.isEmpty {
            defer { event = ""; data = [] }
            guard !data.isEmpty else { return nil }
            return (event.isEmpty ? "message" : event, data.joined(separator: "\n"))
        }
        if line.hasPrefix(":") { return nil }
        let (field, value) = Self.split(line)
        switch field {
        case "event": event = value
        case "data": data.append(value)
        default: break  // "id", "retry": not needed here
        }
        return nil
    }

    private static func split(_ line: String) -> (String, String) {
        guard let colon = line.firstIndex(of: ":") else { return (line, "") }
        var value = line[line.index(after: colon)...]
        if value.hasPrefix(" ") { value = value.dropFirst() }
        return (String(line[..<colon]), String(value))
    }
}

/// Reconnecting reader for `/api/events`. Every (re)connect starts with a fresh snapshot, so a
/// dropped connection never leaves the job list stale.
public struct EventStream: Sendable {
    public let client: APIClient

    public init(client: APIClient) { self.client = client }

    public func events() -> AsyncStream<ServerEvent> {
        AsyncStream { continuation in
            let task = Task {
                var delay: Duration = .milliseconds(500)
                while !Task.isCancelled {
                    do {
                        var request = URLRequest(url: client.base.appending(path: "api/events"))
                        request.timeoutInterval = 60 * 60 * 24
                        let (bytes, _) = try await URLSession.shared.bytes(for: request)
                        delay = .milliseconds(500)
                        var parser = SSEParser()
                        var line = [UInt8]()
                        // Bytes, not `bytes.lines`: that skips the blank lines SSE dispatches on.
                        for try await byte in bytes {
                            if byte == UInt8(ascii: "\n") {
                                if let (name, data) = parser.feed(line: String(decoding: line, as: UTF8.self)),
                                   let event = ServerEvent.decode(name: name, data: data) {
                                    continuation.yield(event)
                                }
                                line.removeAll(keepingCapacity: true)
                            } else {
                                line.append(byte)
                            }
                        }
                    } catch {
                        // The server restarted or is starting: try again, backing off a little.
                    }
                    try? await Task.sleep(for: delay)
                    delay = min(delay * 2, .seconds(5))
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}
