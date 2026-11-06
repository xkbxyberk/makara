import Foundation

/// Where the backend lives and how it is started. Two flavours from one tree:
/// - **development**: the project checkout (`VDProjectRoot`, written into Debug builds), its
///   `.venv` and Homebrew's tools; yt-dlp updates go through the checkout's uv.lock.
/// - **release** (no checkout named): the backend's source inside the app, a uv inside the app,
///   and everything uv and the setup assistant install under
///   `~/Library/Application Support/Makara/runtime` (PLAN P8).
public struct BackendConfig: Sendable, Equatable {
    public var port: Int
    public var projectRoot: URL?
    public var uv: URL?
    public var environment: [String: String]
    public var logFile: URL
    public var release: Release?
    /// The folder name under ~/Library and ~/Movies: "Makara", or "Makara Dev" for a development
    /// build, so the two never share a library (Info.plist `VDAppFolder`).
    public var appFolder = "Makara"

    /// The release flavour's places.
    public struct Release: Sendable, Equatable {
        /// `Contents/Resources`: holds `backend/app` (the server's working directory).
        public var resources: URL
        /// The shipped `pyproject.toml`, `uv.lock` and `.python-version` (read-only, signed).
        public var shippedProject: URL
        /// Python, the venv, the tools, and a writable copy of the project (an in-app yt-dlp
        /// update rewrites its lock).
        public var runtime: URL
        public var uvCache: URL
        /// The tools to install into `bin` (the app's `runtime-manifest.json`).
        public var manifest: RuntimeManifest? = nil

        public var project: URL { runtime.appending(path: "project") }
        public var venv: URL { runtime.appending(path: "venv") }
        public var bin: URL { runtime.appending(path: "bin") }
        public var python: URL { runtime.appending(path: "python") }
    }

    public static let defaultPort = 8787
    /// Finder starts apps with a bare PATH; Homebrew (uv, deno, ffmpeg) must be added back.
    static let extraPath = ["/opt/homebrew/bin", "/usr/local/bin"]
    static let projectFiles = ["pyproject.toml", "uv.lock", ".python-version"]

    /// From the process environment (tests and development override everything with VD_*) and
    /// the app's Info.plist (`VDProjectRoot`, written into Debug builds only).
    public static func resolve(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        infoPlistRoot: String? = Bundle.main.object(forInfoDictionaryKey: "VDProjectRoot") as? String,
        infoPlistPort: String? = Bundle.main.object(forInfoDictionaryKey: "VDPort") as? String,
        appFolder: String = Bundle.main.object(forInfoDictionaryKey: "VDAppFolder") as? String ?? "Makara",
        bundle: URL = Bundle.main.bundleURL,
        fileExists: (String) -> Bool = { FileManager.default.isExecutableFile(atPath: $0) || FileManager.default.fileExists(atPath: $0) },
        home: URL = FileManager.default.homeDirectoryForCurrentUser
    ) -> BackendConfig {
        let port = environment["VD_PORT"].flatMap(Int.init) ?? infoPlistPort.flatMap(Int.init) ?? defaultPort
        let library = home.appending(path: "Library")
        let rootPath = (environment["VD_PROJECT_ROOT"] ?? infoPlistRoot).flatMap { $0.isEmpty ? nil : $0 }
        let root = rootPath
            .map { URL(fileURLWithPath: $0).standardizedFileURL }
            .flatMap { fileExists($0.appending(path: "backend/app/main.py").path) ? $0 : nil }
        // Tests point this elsewhere: they never write into Berk's ~/Library.
        let logFile = environment["VD_LOG_FILE"].map { URL(fileURLWithPath: $0) }
            ?? library.appending(path: "Logs/\(appFolder)/backend.log")
        let resources = bundle.appending(path: "Contents/Resources")
        if root == nil, fileExists(resources.appending(path: "backend/app/main.py").path) {
            // Tests and trial runs name their own runtime, and the uv cache goes beside it.
            let override = environment["VD_RUNTIME_DIR"].map { URL(fileURLWithPath: $0) }
            let runtime = override ?? library.appending(path: "Application Support/\(appFolder)/runtime")
            let cache = override?.appending(path: "uv-cache") ?? library.appending(path: "Caches/\(appFolder)/uv")
            let helper = bundle.appending(path: "Contents/Helpers/uv")
            return BackendConfig(
                port: port, projectRoot: nil,
                uv: fileExists(helper.path) ? helper : nil,
                environment: environment, logFile: logFile,
                release: Release(resources: resources,
                                 shippedProject: resources.appending(path: "backend-project"),
                                 runtime: runtime,
                                 uvCache: cache,
                                 manifest: manifest(environment: environment)),
                appFolder: appFolder)
        }
        return BackendConfig(
            port: port,
            projectRoot: root,
            uv: findUV(environment: environment, fileExists: fileExists, home: home),
            environment: environment,
            logFile: logFile,
            appFolder: appFolder
        )
    }

    /// The shipped manifest; `VD_RUNTIME_BASE_URL` points it elsewhere (a trial with local zips).
    static func manifest(environment: [String: String]) -> RuntimeManifest? {
        guard var manifest = RuntimeManifest.bundled() else { return nil }
        if let base = environment["VD_RUNTIME_BASE_URL"], !base.isEmpty {
            manifest.base = base.hasSuffix("/") ? base : base + "/"
        }
        return manifest
    }

    static func findUV(environment: [String: String], fileExists: (String) -> Bool, home: URL) -> URL? {
        if let explicit = environment["VD_UV"], fileExists(explicit) { return URL(fileURLWithPath: explicit) }
        let path = (environment["PATH"] ?? "").split(separator: ":").map(String.init)
        let candidates = path + extraPath + [home.appending(path: ".local/bin").path, home.appending(path: ".cargo/bin").path]
        return candidates.lazy.map { URL(fileURLWithPath: $0).appending(path: "uv") }.first { fileExists($0.path) }
    }

    /// The server's working directory: the checkout, or the app's Resources (`backend/app`
    /// sits under both, so the backend's own PROJECT_ROOT works the same).
    public var serverDirectory: URL? { projectRoot ?? release?.resources }

    /// Where `uv sync` runs, and how: a release installs no dev tools.
    public var syncDirectory: URL? { projectRoot ?? release?.project }
    public var syncArguments: [String] { release == nil ? ["sync", "--frozen"] : ["sync", "--frozen", "--no-dev"] }

    /// The virtualenv's interpreter: started directly (not through `uv run`) so the app owns
    /// the server process itself and one SIGTERM reaches it exactly once.
    public var python: URL? {
        if let release { return release.venv.appending(path: "bin/python") }
        return projectRoot?.appending(path: ".venv/bin/python")
    }

    /// The server's environment: the app's own (so VD_FIXTURE_MODE, VD_DATA_DIR, … from tests
    /// pass through), Homebrew on PATH, the backend importable, and the app as parent to watch.
    /// A release also tells uv where everything goes, and the backend where its tools and uv are.
    public func serverEnvironment(parentPID: Int32) -> [String: String] {
        // Xcode's debugging variables (library injection, malloc logging) are for the app only.
        var env = environment.filter { key, _ in !key.hasPrefix("DYLD_") && !key.hasPrefix("Malloc") && key != "NSZombieEnabled" }
        let path = (environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin").split(separator: ":").map(String.init)
        env["PATH"] = (Self.extraPath.filter { !path.contains($0) } + path).joined(separator: ":")
        if let projectRoot { env["PYTHONPATH"] = projectRoot.appending(path: "backend").path }
        if let release {
            env["PYTHONPATH"] = release.resources.appending(path: "backend").path
            env["UV_PROJECT_ENVIRONMENT"] = release.venv.path
            env["UV_PYTHON_INSTALL_DIR"] = release.python.path
            env["UV_CACHE_DIR"] = release.uvCache.path
            // Never a Python that happens to be on this Mac (Xcode's, Homebrew's): uv's own.
            env["UV_PYTHON_PREFERENCE"] = "only-managed"
            // Python would otherwise write .pyc files beside the sources, inside the signed app
            // (gotcha 57). The workers inherit this.
            env["PYTHONPYCACHEPREFIX"] = release.runtime.appending(path: "pycache").path
            env["VD_BIN_DIR"] = release.bin.path
            env["VD_UV_PROJECT"] = release.project.path
            if let uv { env["VD_UV"] = uv.path }
        }
        env["VD_PORT"] = String(port)
        env["VD_APP_FOLDER"] = appFolder
        env["VD_PARENT_PID"] = String(parentPID)
        env["PYTHONUNBUFFERED"] = "1"
        return env
    }

    /// A release's writable project: the shipped files, copied again whenever the app brings a
    /// different lock (a new version). Between versions the in-app yt-dlp update owns the copy.
    public func prepareRuntimeProject(fileManager: FileManager = .default) throws {
        guard let release else { return }
        let shippedLock = release.shippedProject.appending(path: "uv.lock")
        let marker = release.project.appending(path: "uv.lock.shipped")
        if let shipped = try? Data(contentsOf: shippedLock), let copied = try? Data(contentsOf: marker), shipped == copied,
           fileManager.fileExists(atPath: release.project.appending(path: "uv.lock").path) {
            return
        }
        try fileManager.createDirectory(at: release.project, withIntermediateDirectories: true)
        for name in Self.projectFiles {
            let target = release.project.appending(path: name)
            try? fileManager.removeItem(at: target)
            try fileManager.copyItem(at: release.shippedProject.appending(path: name), to: target)
        }
        try? fileManager.removeItem(at: marker)
        try fileManager.copyItem(at: shippedLock, to: marker)
    }
}
