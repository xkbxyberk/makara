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
}
