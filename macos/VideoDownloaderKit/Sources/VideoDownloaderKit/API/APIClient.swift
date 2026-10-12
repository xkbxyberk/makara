import Foundation

public struct APIError: Error, Equatable, Sendable {
    public let code: String
    public let raw: String
}

/// A thin async client for the local backend. Never talks to anything but 127.0.0.1.
public struct APIClient: Sendable {
    public let base: URL
    private let session: URLSession

    public init(port: Int, session: URLSession = .shared) {
        self.base = URL(string: "http://127.0.0.1:\(port)")!
        self.session = session
    }

    public func get<T: Decodable>(_ path: String, as type: T.Type = T.self, timeout: TimeInterval = 10) async throws -> T {
        var request = URLRequest(url: base.appending(path: path))
        request.timeoutInterval = timeout
        let (data, response) = try await session.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            if let body = try? JSON.decoder.decode(APIErrorBody.self, from: data) {
                throw APIError(code: body.error.code, raw: body.error.raw ?? "")
            }
            throw APIError(code: "HTTP_\(status)", raw: String(decoding: data, as: UTF8.self))
        }
        return try JSON.decoder.decode(T.self, from: data)
    }

    public func health(timeout: TimeInterval = 1) async -> Health? {
        try? await get("api/health", as: Health.self, timeout: timeout)
    }

    public func settings() async throws -> AppSettings {
        try await get("api/settings")
    }
}
