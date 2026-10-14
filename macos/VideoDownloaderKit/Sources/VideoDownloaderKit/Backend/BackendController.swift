import Darwin
import Foundation
import Observation

/// Why the backend is not running, in terms the UI can explain and act on.
public enum BackendFailure: Equatable, Sendable {
    case noProject
    case noPython
    case syncFailed(Int32)
    case exited(Int32)
    case timedOut(seconds: Int)
    case portBusy(Int)
    case spawnFailed(Int32)
    /// It was running (ours or attached) and stopped answering.
    case lost
}

public enum BackendState: Equatable, Sendable {
    case idle
    /// A release whose tools are not installed yet: the setup assistant asks before anything
    /// is downloaded.
    case needsSetup
    case syncing
    case starting
    /// `attached`: a server was already answering on the port (a development server, or one
    /// left by an earlier run); the app uses it and does not stop it on quit.
    case ready(attached: Bool)
    case failed(BackendFailure)
    case stopped
}

/// Starts, watches and stops the Python backend.
@MainActor
@Observable
public final class BackendController {
    public private(set) var state: BackendState = .idle
    public let config: BackendConfig
    public var client: APIClient { APIClient(port: config.port) }
    /// Called when a ready backend goes away, so the app can drop what it showed from it.
    @ObservationIgnored public var onLost: (() -> Void)?

    @ObservationIgnored private var process: ChildProcess?
    @ObservationIgnored private var monitor: Task<Void, Never>?
    @ObservationIgnored private var busy = false
    static let startTimeout = 60
    static let healthEvery: Duration = .seconds(2)
    /// Missed health checks in a row before a ready backend counts as gone.
    static let missesAllowed = 2

    public init(config: BackendConfig) {
        self.config = config
    }

    /// Bring the backend up, or explain why not. A second call while one runs does nothing.
    public func start() async {
        if case .ready = state { return }
        guard !busy else { return }
        busy = true
        defer { busy = false }
        await bringUp()
        if case .ready = state { watch() }
    }

    private func bringUp() async {
        // Something already answers? Use it -- unless it is not ours.
        switch await probe() {
        case .ours:
            state = .ready(attached: true)
            return
        case .foreign:
            state = .failed(.portBusy(config.port))
            return
        case .free:
            break
        }
        guard let root = config.serverDirectory, let syncDirectory = config.syncDirectory else {
            state = .failed(.noProject)
            return
        }
        if let release = config.release, !RuntimeTools.ready(release) {
            state = .needsSetup
            return
        }
        rotateLog()
        let environment = config.serverEnvironment(parentPID: getpid())
        let existing = runnablePython()
        // `uv sync --frozen`: the venv exactly as uv.lock says (an in-app yt-dlp update changes
        // the lock), never re-locking. If it fails but a venv exists, start with that. In a
        // release this is also what installs Python and every package the first time.
        if let uv = config.uv {
            state = .syncing
            do {
                try config.prepareRuntimeProject()
                let sync = try ChildProcess.spawn(executable: uv, arguments: config.syncArguments, directory: syncDirectory,
                                                  environment: environment, log: config.logFile)
                let code = await sync.waitForExit()
                if code != 0, existing == nil {
                    state = .failed(.syncFailed(code))
                    return
                }
            } catch {
                if existing == nil {
                    state = .failed(.spawnFailed(Self.errno(of: error)))
                    return
                }
            }
        }
        // Looked up again: the first sync of a release is what creates the venv.
        guard let python = runnablePython() else {
            state = .failed(.noPython)
            return
        }
        state = .starting
        let child: ChildProcess
        do {
            child = try ChildProcess.spawn(executable: python, arguments: ["-m", "app.main"], directory: root,
                                           environment: environment, log: config.logFile)
        } catch {
            state = .failed(.spawnFailed(Self.errno(of: error)))
            return
        }
        process = child
        let deadline = ContinuousClock.now + .seconds(Self.startTimeout)
        while ContinuousClock.now < deadline {
            if let code = child.exitStatus {
                process = nil
                state = .failed(.exited(code))
                return
            }
            if await client.health(timeout: 0.5) != nil {
                state = .ready(attached: false)
                return
            }
            try? await Task.sleep(for: .milliseconds(200))
        }
        process = nil
        await child.stop(grace: .seconds(3))
        state = .failed(.timedOut(seconds: Self.startTimeout))
    }

    /// Stop what we started (never an attached server). Safe to call more than once.
    public func stop() async {
        monitor?.cancel()
        monitor = nil
        guard let process else {
            if case .ready = state { state = .stopped }
            return
        }
        self.process = nil
        await process.stop()
        state = .stopped
    }

    /// Stop, then leave the controller ready for a fresh `start()` (which the caller makes).
    public func reset() async {
        await stop()
        state = .idle
    }

    /// While ready: our own server exiting, or any server (ours or attached) no longer
    /// answering, is reported -- never a silent "ready" over a dead backend.
    private func watch() {
        monitor?.cancel()
        let owned = process
        monitor = Task { [weak self] in
            var misses = 0
            while !Task.isCancelled {
                try? await Task.sleep(for: Self.healthEvery)
                guard !Task.isCancelled, let self else { return }
                if let owned, let code = owned.exitStatus {
                    self.lose(.exited(code))
                    return
                }
                misses = await self.client.health(timeout: 1.5) == nil ? misses + 1 : 0
                if misses >= Self.missesAllowed {
                    if let owned {
                        self.process = nil
                        await owned.stop(grace: .seconds(3))
                    }
                    self.lose(.lost)
                    return
                }
            }
        }
    }

    private func lose(_ failure: BackendFailure) {
        guard case .ready = state else { return }
        process = nil
        state = .failed(failure)
        onLost?()
    }

    private enum Probe { case ours, foreign, free }

    private func probe() async -> Probe {
        var request = URLRequest(url: client.base.appending(path: "api/health"))
        request.timeoutInterval = 1
        guard let (data, response) = try? await URLSession.shared.data(for: request) else { return .free }
        let ok = (response as? HTTPURLResponse)?.statusCode == 200
            && (try? JSON.decoder.decode(Health.self, from: data)) != nil
        return ok ? .ours : .foreign
    }

    private func runnablePython() -> URL? {
        config.python.flatMap { FileManager.default.isExecutableFile(atPath: $0.path) ? $0 : nil }
    }

    private static func errno(of error: Error) -> Int32 {
        (error as? POSIXError).map { Int32($0.code.rawValue) } ?? -1
    }

    /// One previous log is kept next to the current one.
    private func rotateLog() {
        let fm = FileManager.default
        let previous = config.logFile.deletingPathExtension().appendingPathExtension("previous.log")
        try? fm.removeItem(at: previous)
        try? fm.moveItem(at: config.logFile, to: previous)
    }

    /// The last lines of the log, for the failure screen.
    public func logTail(lines: Int = 12) -> String {
        guard let text = try? String(contentsOf: config.logFile, encoding: .utf8) else { return "" }
        return text.split(separator: "\n", omittingEmptySubsequences: false).suffix(lines).joined(separator: "\n")
    }
}
