import Foundation
import Testing
@testable import VideoDownloaderKit

struct BackendConfigTests {
    let home = URL(fileURLWithPath: "/Users/someone")

    @Test func overridesComeFromTheEnvironmentFirst() {
        let config = BackendConfig.resolve(
            environment: ["VD_PORT": "8789", "VD_PROJECT_ROOT": "/repo", "PATH": "/usr/bin:/bin"],
            infoPlistRoot: "/elsewhere",
            fileExists: { $0 == "/repo/backend/app/main.py" || $0 == "/opt/homebrew/bin/uv" },
            home: home)
        #expect(config.port == 8789)
        #expect(config.projectRoot?.path == "/repo")
        #expect(config.uv?.path == "/opt/homebrew/bin/uv")
        #expect(config.python?.path == "/repo/.venv/bin/python")
    }

    @Test func aRootWithoutTheBackendIsNoRoot() {
        let config = BackendConfig.resolve(environment: [:], infoPlistRoot: "/nowhere", fileExists: { _ in false }, home: home)
        #expect(config.projectRoot == nil)
        #expect(config.port == BackendConfig.defaultPort)
        #expect(config.uv == nil)
    }

    @Test func uvIsFoundOnPathOrInTheUsualPlaces() {
        let config = BackendConfig.resolve(environment: ["PATH": "/custom/bin"], infoPlistRoot: nil,
                                           fileExists: { $0 == "/Users/someone/.local/bin/uv" }, home: home)
        #expect(config.uv?.path == "/Users/someone/.local/bin/uv")
    }

    @Test func theServerGetsHomebrewOnPathTheBackendAndItsParent() {
        let config = BackendConfig.resolve(environment: ["PATH": "/usr/bin:/bin", "VD_FIXTURE_MODE": "1"],
                                           infoPlistRoot: "/repo", fileExists: { _ in true }, home: home)
        let env = config.serverEnvironment(parentPID: 4242)
        #expect(env["PATH"] == "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin")
        #expect(env["PYTHONPATH"] == "/repo/backend")
        #expect(env["VD_PARENT_PID"] == "4242")
        #expect(env["VD_PORT"] == "8787")
        #expect(env["VD_FIXTURE_MODE"] == "1")  // test settings pass through
    }

    // ---- release flavour (PLAN P8) ------------------------------------------------------------

    let app = URL(fileURLWithPath: "/Applications/Makara.app")

    @Test func withoutACheckoutTheAppRunsTheBackendItCarries() {
        let config = BackendConfig.resolve(
            environment: ["PATH": "/usr/bin:/bin"], infoPlistRoot: "", bundle: app,
            fileExists: { $0 == "/Applications/Makara.app/Contents/Resources/backend/app/main.py"
                || $0 == "/Applications/Makara.app/Contents/Helpers/uv" || $0 == "/opt/homebrew/bin/uv" },
            home: home)
        let runtime = "/Users/someone/Library/Application Support/Makara/runtime"
        #expect(config.projectRoot == nil)
        #expect(config.release?.runtime.path == runtime)
        #expect(config.uv?.path == "/Applications/Makara.app/Contents/Helpers/uv")  // never Homebrew's
        #expect(config.python?.path == runtime + "/venv/bin/python")
        #expect(config.serverDirectory?.path == "/Applications/Makara.app/Contents/Resources")
        #expect(config.syncDirectory?.path == runtime + "/project")
        #expect(config.syncArguments == ["sync", "--frozen", "--no-dev"])

        let env = config.serverEnvironment(parentPID: 1)
        #expect(env["PYTHONPATH"] == "/Applications/Makara.app/Contents/Resources/backend")
        #expect(env["UV_PROJECT_ENVIRONMENT"] == runtime + "/venv")
        #expect(env["UV_PYTHON_INSTALL_DIR"] == runtime + "/python")
        #expect(env["UV_PYTHON_PREFERENCE"] == "only-managed")
        #expect(env["PYTHONPYCACHEPREFIX"] == runtime + "/pycache")  // never inside the signed app
        #expect(env["VD_BIN_DIR"] == runtime + "/bin")
        #expect(env["VD_UV_PROJECT"] == runtime + "/project")
        #expect(env["VD_UV"] == "/Applications/Makara.app/Contents/Helpers/uv")
    }

    @Test func aCheckoutWinsOverTheCarriedBackend() {
        let config = BackendConfig.resolve(environment: [:], infoPlistRoot: "/repo", bundle: app,
                                           fileExists: { _ in true }, home: home)
        #expect(config.release == nil)
        #expect(config.projectRoot?.path == "/repo")
        #expect(config.syncArguments == ["sync", "--frozen"])
        #expect(config.serverEnvironment(parentPID: 1)["VD_BIN_DIR"] == nil)
    }

    @Test func theWritableProjectIsReplacedOnlyWhenTheAppBringsAnotherLock() throws {
        let base = FileManager.default.temporaryDirectory.appending(path: "vd-release-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: base) }
        let shipped = base.appending(path: "shipped")
        try FileManager.default.createDirectory(at: shipped, withIntermediateDirectories: true)
        for name in BackendConfig.projectFiles { try Data("v1 \(name)".utf8).write(to: shipped.appending(path: name)) }
        let release = BackendConfig.Release(resources: base, shippedProject: shipped, runtime: base.appending(path: "runtime"),
                                            uvCache: base.appending(path: "cache"))
        let config = BackendConfig(port: 1, projectRoot: nil, uv: nil, environment: [:], logFile: base, release: release)
        let lock = release.project.appending(path: "uv.lock")

        try config.prepareRuntimeProject()
        #expect(try String(contentsOf: lock, encoding: .utf8) == "v1 uv.lock")
        try Data("updated in the app".utf8).write(to: lock)  // the in-app yt-dlp update
        try config.prepareRuntimeProject()
        #expect(try String(contentsOf: lock, encoding: .utf8) == "updated in the app")
        try Data("v2 uv.lock".utf8).write(to: shipped.appending(path: "uv.lock"))  // a new app version
        try config.prepareRuntimeProject()
        #expect(try String(contentsOf: lock, encoding: .utf8) == "v2 uv.lock")
    }
}
