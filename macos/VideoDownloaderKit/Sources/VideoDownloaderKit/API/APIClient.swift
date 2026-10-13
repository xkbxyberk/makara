import Foundation

public struct APIError: Error, Equatable, Sendable {
    public let code: String
    public let raw: String

    public init(code: String, raw: String = "") {
        self.code = code
        self.raw = raw
    }

    /// Any failure as a code the UI can word: the backend's own, or NETWORK when it did not answer (as the web page does).
    public static func from(_ error: Error) -> APIError {
        if let error = error as? APIError { return error }
        if error is URLError { return APIError(code: "NETWORK", raw: error.localizedDescription) }
        return APIError(code: "UNKNOWN", raw: String(describing: error))
    }
}

/// A thin async client for the local backend. Never talks to anything but 127.0.0.1.
public struct APIClient: Sendable {
    public let base: URL
    private let session: URLSession

    public init(port: Int, session: URLSession = .shared) {
        self.base = URL(string: "http://127.0.0.1:\(port)")!
        self.session = session
    }

    public func get<T: Decodable>(_ path: String, as type: T.Type = T.self, timeout: TimeInterval = 10,
                                  decoder: JSONDecoder = JSON.decoder) async throws -> T {
        try await send(request(path, method: "GET", timeout: timeout), decoder: decoder)
    }

    public func post<T: Decodable>(_ path: String, body: [String: any Sendable] = [:], as type: T.Type = T.self,
                                   timeout: TimeInterval = 10) async throws -> T {
        var request = request(path, method: "POST", timeout: timeout)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        return try await send(request, decoder: JSON.decoder)
    }

    /// A body the models describe (sent snake-cased, as the backend names its fields).
    public func post<T: Decodable, B: Encodable>(_ path: String, json body: B, as type: T.Type = T.self,
                                                 timeout: TimeInterval = 10, decoder: JSONDecoder = JSON.decoder) async throws -> T {
        var request = request(path, method: "POST", timeout: timeout)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSON.encoder.encode(body)
        return try await send(request, decoder: decoder)
    }

    public func delete<T: Decodable>(_ path: String, as type: T.Type = T.self) async throws -> T {
        try await send(request(path, method: "DELETE", timeout: 10), decoder: JSON.decoder)
    }

    private func request(_ path: String, method: String, timeout: TimeInterval) -> URLRequest {
        var request = URLRequest(url: base.appending(path: path))
        request.httpMethod = method
        request.timeoutInterval = timeout
        return request
    }

    private func send<T: Decodable>(_ request: URLRequest, decoder: JSONDecoder) async throws -> T {
        let (data, response) = try await session.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            if let body = try? JSON.decoder.decode(APIErrorBody.self, from: data) {
                throw APIError(code: body.error.code, raw: body.error.raw ?? "")
            }
            throw APIError(code: "HTTP_\(status)", raw: String(decoding: data, as: UTF8.self))
        }
        return try decoder.decode(T.self, from: data)
    }

    public func health(timeout: TimeInterval = 1) async -> Health? {
        try? await get("api/health", as: Health.self, timeout: timeout)
    }

    public func settings() async throws -> AppSettings {
        try await get("api/settings")
    }

    // ---- jobs -------------------------------------------------------------------------------

    struct OK: Decodable { let ok: Bool }
    struct Shown: Decodable { let shown: Bool }

    private func job(_ id: String) -> String {
        "api/jobs/" + (id.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? id)
    }

    public func cancel(job id: String) async throws {
        _ = try await post(job(id) + "/cancel", as: Job.self)
    }

    public func retry(job id: String) async throws {
        _ = try await post(job(id) + "/retry", as: Job.self)
    }

    /// From the list only: the downloaded files stay where they are.
    public func remove(job id: String) async throws {
        _ = try await delete(job(id), as: OK.self)
    }

    /// Selects one output file in Finder; the backend checks it is inside that job's folder.
    public func reveal(job id: String, file index: Int) async throws {
        _ = try await post(job(id) + "/reveal", body: ["index": index], as: Shown.self)
    }

    // ---- inspect and download ---------------------------------------------------------------

    struct InspectBody: Encodable {
        let url: String
        let rule: QuickRule?

        func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(url, forKey: .url)
            try c.encode(rule, forKey: .rule)  // null, not absent, when there is none
        }

        enum CodingKeys: String, CodingKey { case url, rule }
    }

    /// Runs yt-dlp against the site (the backend caches the answer for a while).
    public func inspect(_ url: String, rule: QuickRule?) async throws -> InspectResult {
        try await post("api/inspect", json: InspectBody(url: url, rule: rule), timeout: Self.inspectTimeout)
    }

    /// The backend gives the inspect worker 180 s, and a video that needs the Safari session is
    /// inspected twice (once without, once with): wait a little more than both.
    public static let inspectTimeout: TimeInterval = 400

    public func plan(_ selection: Selection) async throws -> Plan {
        try await post("api/plan", json: selection, decoder: JSON.plain)
    }

    public func createJob(_ selection: Selection) async throws -> Job {
        try await post("api/jobs", json: selection)
    }

    // ---- system -----------------------------------------------------------------------------

    public func doctor() async throws -> DoctorReport {
        try await get("api/doctor", timeout: 60, decoder: JSON.plain)
    }

    /// `uv lock --upgrade-package yt-dlp …` then `uv sync`. Nothing is sent until both finish,
    /// and the backend gives each step 600 s: wait longer than that, or a slow update reads as
    /// "no connection" while it still runs.
    public static let updateTimeout: TimeInterval = 1_260

    public func updateYtdlp() async throws -> UpdateResult {
        try await post("api/system/update-ytdlp", timeout: Self.updateTimeout)
    }

    public func openFullDiskAccess() async throws {
        _ = try await post("api/system/open-full-disk-access", as: OK.self)
    }
}
