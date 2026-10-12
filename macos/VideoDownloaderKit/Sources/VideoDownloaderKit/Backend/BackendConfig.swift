import Foundation

/// Where the backend lives and how it is started. The app runs the backend from this project
/// checkout (personal use; yt-dlp updates go through its uv.lock), never a copy of it.
public struct BackendConfig: Sendable, Equatable {
    public var port: Int
    public var projectRoot: URL?
    public var uv: URL?
    public var environment: [String: String]
    public var logFile: URL

    public static let defaultPort = 8787
    /// Finder starts apps with a bare PATH; Homebrew (uv, deno, ffmpeg) must be added back.
    static let extraPath = ["/opt/homebrew/bin", "/usr/local/bin"]

    /// From the process environment (tests and development override everything with VD_*) and
    /// the app's Info.plist (`VDProjectRoot`, written at build time).
    public static func resolve(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        infoPlistRoot: String? = Bundle.main.object(forInfoDictionaryKey: "VDProjectRoot") as? String,
        fileExists: (String) -> Bool = { FileManager.default.isExecutableFile(atPath: $0) || FileManager.default.fileExists(atPath: $0) },
        home: URL = FileManager.default.homeDirectoryForCurrentUser
    ) -> BackendConfig {
        let port = environment["VD_PORT"].flatMap(Int.init) ?? defaultPort
        let rootPath = environment["VD_PROJECT_ROOT"] ?? infoPlistRoot
        let root = rootPath
            .map { URL(fileURLWithPath: $0).standardizedFileURL }
            .flatMap { fileExists($0.appending(path: "backend/app/main.py").path) ? $0 : nil }
        return BackendConfig(
            port: port,
            projectRoot: root,
            uv: findUV(environment: environment, fileExists: fileExists, home: home),
            environment: environment,
            // Tests point this elsewhere: they never write into Berk's ~/Library.
            logFile: environment["VD_LOG_FILE"].map { URL(fileURLWithPath: $0) }
                ?? home.appending(path: "Library/Logs/VideoDownloader/backend.log")
        )
    }

    static func findUV(environment: [String: String], fileExists: (String) -> Bool, home: URL) -> URL? {
        if let explicit = environment["VD_UV"], fileExists(explicit) { return URL(fileURLWithPath: explicit) }
        let path = (environment["PATH"] ?? "").split(separator: ":").map(String.init)
        let candidates = path + extraPath + [home.appending(path: ".local/bin").path, home.appending(path: ".cargo/bin").path]
        return candidates.lazy.map { URL(fileURLWithPath: $0).appending(path: "uv") }.first { fileExists($0.path) }
    }

    /// The virtualenv's interpreter: started directly (not through `uv run`) so the app owns
    /// the server process itself and one SIGTERM reaches it exactly once.
    public var python: URL? { projectRoot?.appending(path: ".venv/bin/python") }

    /// The server's environment: the app's own (so VD_FIXTURE_MODE, VD_DATA_DIR, … from tests
    /// pass through), Homebrew on PATH, the backend importable, and the app as parent to watch.
    public func serverEnvironment(parentPID: Int32) -> [String: String] {
        // Xcode's debugging variables (library injection, malloc logging) are for the app only.
        var env = environment.filter { key, _ in !key.hasPrefix("DYLD_") && !key.hasPrefix("Malloc") && key != "NSZombieEnabled" }
        let path = (environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin").split(separator: ":").map(String.init)
        env["PATH"] = (Self.extraPath.filter { !path.contains($0) } + path).joined(separator: ":")
        if let projectRoot { env["PYTHONPATH"] = projectRoot.appending(path: "backend").path }
        env["VD_PORT"] = String(port)
        env["VD_PARENT_PID"] = String(parentPID)
        env["PYTHONUNBUFFERED"] = "1"
        return env
    }
}
