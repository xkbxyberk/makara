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

    /// Validated by the backend (an unsafe folder, a template that escapes it): a code if not.
    public func save(_ settings: AppSettings) async throws -> AppSettings {
        var request = request("api/settings", method: "PUT", timeout: 10)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSON.encoder.encode(settings)
        return try await send(request, decoder: JSON.decoder)
    }

    struct TemplatePreview: Decodable { let filename: String }

    /// The file name a template gives for the sample video (the words come from the catalog).
    public func previewTemplate(_ template: String, sample: [String: String]) async throws -> String {
        try await post("api/settings/preview-template", body: ["template": template, "sample": sample, "ext": "mkv"],
                       as: TemplatePreview.self).filename
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

    // ---- library ----------------------------------------------------------------------------

    private func item(_ id: String) -> String {
        "api/library/" + (id.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? id)
    }

    public func library(_ query: LibraryQuery) async throws -> LibraryPage {
        var request = URLRequest(url: base.appending(path: "api/library").appending(queryItems: query.items))
        request.timeoutInterval = 10
        return try await send(request, decoder: JSON.decoder)
    }

    /// Looks for every item's file: marks vanished ones missing, re-links moved ones.
    public func scanLibrary() async throws -> ScanResult {
        try await post("api/library/scan", timeout: 900)  // ffprobe over a big library takes a while
    }

    /// In the default player (IINA, QuickTime…); there is deliberately no player in the app.
    public func open(item id: String) async throws {
        _ = try await post(item(id) + "/open", as: Opened.self)
    }

    public func reveal(item id: String) async throws {
        _ = try await post(item(id) + "/reveal", as: Shown.self)
    }

    /// To the macOS Trash (recoverable). The screen asks first.
    public func trash(item id: String) async throws {
        _ = try await post(item(id) + "/trash", as: LibraryItem.self)
    }

    /// A missing item's record only; refused (ITEM_NOT_MISSING) while its file is back.
    public func forget(item id: String) async throws {
        _ = try await post(item(id) + "/forget", as: OK.self)
    }

    public struct Forgotten: Decodable, Sendable { public let removed: Int; public let kept: Int }

    public func forgetMissing() async throws -> Forgotten {
        try await post("api/library/forget-missing")
    }

    public func thumbnailURL(item id: String) -> URL { base.appending(path: item(id) + "/thumbnail") }

    struct Opened: Decodable { let opened: Bool }

    // ---- studio -----------------------------------------------------------------------------

    /// A file on this Mac, or a library item's file.
    public func studioProbe(path: String? = nil, item: String? = nil) async throws -> StudioSource {
        var body: [String: any Sendable] = [:]
        if let path { body["path"] = path }
        if let item { body["item_id"] = item }
        return try await post("api/studio/probe", body: body, timeout: 60)
    }

    /// The exact FFmpeg plan for a request (`StudioRequest.body`).
    public func studioPlan(_ body: [String: any Sendable]) async throws -> StudioPlan {
        var request = request("api/studio/plan", method: "POST", timeout: 60)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        return try await send(request, decoder: JSON.plain)
    }

    public func studioJob(_ body: [String: any Sendable]) async throws -> Job {
        try await post("api/studio/jobs", body: body, timeout: 60)
    }

    /// Every keyframe of the source's video (where a lossless cut can start), in seconds.
    public func keyframes(path: String) async throws -> [Double] {
        try await post("api/studio/keyframes", body: ["path": path], as: Keyframes.self, timeout: 200).times
    }

    public func startPreview(path: String) async throws -> PreviewStatus {
        try await post("api/studio/preview", body: ["path": path], timeout: 60)
    }

    public func preview(path: String) async throws -> PreviewStatus {
        try await post("api/studio/preview/status", body: ["path": path])
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
