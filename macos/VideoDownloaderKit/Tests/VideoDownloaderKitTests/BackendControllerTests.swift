import Foundation
import Network
import Testing
@testable import VideoDownloaderKit

/// The controller against fake projects, a fake uv and fake servers: never the real backend.
@MainActor
struct BackendControllerTests {
    let scratch = FileManager.default.temporaryDirectory.appending(path: "vd-backend-\(UUID().uuidString)")

    func port() -> Int { Int.random(in: 20000...29999) }

    /// A project folder with the files BackendConfig checks for, and a uv that only records
    /// that it ran and fails.
    func fakeProject() throws -> (root: URL, uv: URL, calls: URL) {
        let root = scratch.appending(path: "repo")
        try FileManager.default.createDirectory(at: root.appending(path: "backend/app"), withIntermediateDirectories: true)
        try Data().write(to: root.appending(path: "backend/app/main.py"))
        let calls = scratch.appending(path: "uv-calls")
        let uv = scratch.appending(path: "uv")
        try "#!/bin/sh\necho \"$@\" >> \(calls.path)\nexit 7\n".write(to: uv, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: uv.path)
        return (root, uv, calls)
    }

    func config(port: Int, root: URL? = nil, uv: URL? = nil) -> BackendConfig {
        BackendConfig(port: port, projectRoot: root, uv: uv, environment: ["PATH": "/usr/bin:/bin"],
                      logFile: scratch.appending(path: "backend.log"))
    }

    @Test func noProjectIsExplained() async {
        let backend = BackendController(config: config(port: port()))
        await backend.start()
        #expect(backend.state == .failed(.noProject))
    }

    @Test func aFailedSyncWithoutAVenvIsExplainedAndRetryRunsItOnce() async throws {
        let project = try fakeProject()
        let backend = BackendController(config: config(port: port(), root: project.root, uv: project.uv))
        await backend.start()
        #expect(backend.state == .failed(.syncFailed(7)))
        await backend.reset()
        await backend.start()
        let calls = try String(contentsOf: project.calls, encoding: .utf8).split(separator: "\n")
        #expect(calls == ["sync --frozen", "sync --frozen"])  // one per attempt, never two
    }

    /// A release's first start has no venv until uv sync made it: the server must still start.
    @Test func theVenvTheFirstSyncCreatesIsUsed() async throws {
        let project = try fakeProject()
        let python = project.root.appending(path: ".venv/bin/python")
        try """
            #!/bin/sh
            mkdir -p \(python.deletingLastPathComponent().path)
            printf '#!/bin/sh\\nexit 3\\n' > \(python.path)
            chmod 755 \(python.path)
            """.write(to: project.uv, atomically: true, encoding: .utf8)
        let backend = BackendController(config: config(port: port(), root: project.root, uv: project.uv))
        await backend.start()
        #expect(backend.state == .failed(.exited(3)))  // it ran the new interpreter, not "no Python"
    }

    @Test func aSecondStartWhileOneRunsDoesNothing() async throws {
        let project = try fakeProject()
        let backend = BackendController(config: config(port: port(), root: project.root, uv: project.uv))
        async let first: Void = backend.start()
        async let second: Void = backend.start()
        _ = await (first, second)
        let calls = try String(contentsOf: project.calls, encoding: .utf8).split(separator: "\n")
        #expect(calls.count == 1)
    }

    @Test func somethingElseOnThePortIsNotMistakenForTheBackend() async throws {
        let server = try FakeHTTPServer(body: "<html>not us</html>")
        defer { server.stop() }
        let backend = BackendController(config: config(port: server.port))
        await backend.start()
        #expect(backend.state == .failed(.portBusy(server.port)))
    }

    @Test func anAttachedServerThatGoesAwayIsReportedNotTrusted() async throws {
        let server = try FakeHTTPServer(body: #"{"ok":true,"fixture_mode":true}"#)
        let backend = BackendController(config: config(port: server.port))
        var lost = false
        backend.onLost = { lost = true }
        await backend.start()
        #expect(backend.state == .ready(attached: true))
        server.stop()
        for _ in 0..<80 where backend.state == .ready(attached: true) {
            try await Task.sleep(for: .milliseconds(100))
        }
        #expect(backend.state == .failed(.lost))
        #expect(lost)
        await backend.stop()  // never stops a server it did not start; must not hang either
    }
}

/// A one-route HTTP server on 127.0.0.1 answering every request with `body`.
final class FakeHTTPServer: @unchecked Sendable {
    let port: Int
    private let listener: NWListener

    init(body: String) throws {
        let chosen = Int.random(in: 30000...39999)
        let parameters = NWParameters.tcp
        parameters.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: NWEndpoint.Port(rawValue: UInt16(chosen))!)
        listener = try NWListener(using: parameters)
        port = chosen
        let response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: \(body.utf8.count)\r\nConnection: close\r\n\r\n\(body)"
        listener.newConnectionHandler = { connection in
            connection.start(queue: .global())
            connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { _, _, _, _ in
                connection.send(content: Data(response.utf8), completion: .contentProcessed { _ in connection.cancel() })
            }
        }
        let ready = DispatchSemaphore(value: 0)
        listener.stateUpdateHandler = { if case .ready = $0 { ready.signal() } }
        listener.start(queue: .global())
        _ = ready.wait(timeout: .now() + 5)
    }

    func stop() { listener.cancel() }
}
