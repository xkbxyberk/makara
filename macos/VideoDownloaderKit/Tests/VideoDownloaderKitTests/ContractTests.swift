import Foundation
import Testing
@testable import VideoDownloaderKit

/// The backend's real responses (written by tests/test_api_samples.py) decode into the
/// app's models. If the API changes shape, this fails before the app does.
struct ContractTests {
    static let samples = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
        .appending(path: "tests/fixtures/api")

    func sample(_ name: String) throws -> Data {
        try Data(contentsOf: Self.samples.appending(path: "\(name).json"))
    }

    @Test func health() throws {
        let health = try JSON.decoder.decode(Health.self, from: sample("health"))
        #expect(health == Health(ok: true, fixtureMode: true))
    }

    @Test func settings() throws {
        let settings = try JSON.decoder.decode(AppSettings.self, from: sample("settings"))
        #expect(settings.defaultMode == "mkv")
        #expect(settings.notifications)
    }

    @Test func jobs() throws {
        let jobs = try JSON.decoder.decode([Job].self, from: sample("jobs"))
        let job = try #require(jobs.first)
        #expect(job.status == .done)
        #expect(job.title == "Local test clip")
        #expect(job.outputFiles.count == 1)
    }

    @Test func jobEventDecodesThroughTheSSEPath() throws {
        let text = String(decoding: try sample("event-job"), as: UTF8.self)
        guard case .job(let job)? = ServerEvent.decode(name: "job", data: text) else {
            Issue.record("not a job event")
            return
        }
        #expect(job.status == .done)
    }

    @Test func errorBody() throws {
        let body = try JSON.decoder.decode(APIErrorBody.self, from: sample("error"))
        #expect(body.error.code == "QUICK_NEEDS_SOURCE")
    }

    @Test func supports() throws {
        let answer = try JSON.decoder.decode(Supports.self, from: sample("supports"))
        #expect(answer.supported)
    }

    @Test func everySampleIsCoveredByATest() throws {
        let names = try FileManager.default.contentsOfDirectory(atPath: Self.samples.path)
            .filter { $0.hasSuffix(".json") }.sorted()
        #expect(names == ["error.json", "event-job.json", "health.json", "jobs.json", "settings.json", "supports.json"])
    }

    @Test func anUnknownJobStatusDoesNotBreakDecoding() throws {
        let json = #"{"id":"x","kind":"download","status":"paused","output_files":[]}"#
        let job = try JSON.decoder.decode(Job.self, from: Data(json.utf8))
        #expect(job.status == .unknown)
    }
}
