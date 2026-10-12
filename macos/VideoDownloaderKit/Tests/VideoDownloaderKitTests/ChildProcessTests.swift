import Foundation
import Testing
@testable import VideoDownloaderKit

struct ChildProcessTests {
    let log = FileManager.default.temporaryDirectory.appending(path: "vd-child-\(UUID().uuidString).log")

    @Test func outputGoesToTheLogAndTheExitCodeIsReported() async throws {
        let child = try ChildProcess.spawn(executable: URL(fileURLWithPath: "/bin/sh"), arguments: ["-c", "echo hello; echo oops >&2; exit 3"],
                                           directory: URL(fileURLWithPath: "/tmp"), environment: [:], log: log)
        #expect(await child.waitForExit() == 3)
        let text = try String(contentsOf: log, encoding: .utf8)
        #expect(text.contains("hello") && text.contains("oops"))
    }

    @Test func stopReachesTheWholeGroupAndEscalatesToKill() async throws {
        // A child that ignores SIGTERM and has a grandchild: both must be gone after stop().
        let marker = FileManager.default.temporaryDirectory.appending(path: "vd-grandchild-\(UUID().uuidString)")
        let script = "trap '' TERM; (trap '' TERM; echo $$ > \(marker.path); sleep 60) & sleep 60"
        let child = try ChildProcess.spawn(executable: URL(fileURLWithPath: "/bin/sh"), arguments: ["-c", script],
                                           directory: URL(fileURLWithPath: "/tmp"), environment: [:], log: log)
        var grandchild: pid_t = 0
        for _ in 0..<50 where grandchild == 0 {
            try await Task.sleep(for: .milliseconds(50))
            grandchild = pid_t((try? String(contentsOf: marker, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "") ?? 0
        }
        #expect(grandchild != 0)
        await child.stop(grace: .milliseconds(300))
        #expect(child.exitStatus != nil)
        try await Task.sleep(for: .milliseconds(200))
        #expect(kill(grandchild, 0) != 0, "the grandchild survived")
    }
}
