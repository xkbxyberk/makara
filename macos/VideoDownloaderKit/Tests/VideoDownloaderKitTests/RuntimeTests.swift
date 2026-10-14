import Foundation
import Testing
@testable import VideoDownloaderKit

/// The setup assistant's installer against a local zip of fake tools: never the network.
struct RuntimeTests {
    let scratch = FileManager.default.temporaryDirectory.appending(path: "vd-runtime-\(UUID().uuidString)")

    /// A zip like the real one (bin/ with the four tools, LICENSES/), each tool a script that
    /// exits with `status`; its manifest entry for this Mac.
    func archive(status: Int = 0) throws -> (zip: URL, entry: RuntimeManifest.Archive) {
        let stage = scratch.appending(path: "stage-\(status)")
        try FileManager.default.createDirectory(at: stage.appending(path: "bin"), withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: stage.appending(path: "LICENSES"), withIntermediateDirectories: true)
        for tool in RuntimeTools.tools {
            let path = stage.appending(path: "bin/\(tool.name)")
            try "#!/bin/sh\nexit \(tool.name == "deno" ? status : 0)\n".write(to: path, atomically: true, encoding: .utf8)
            try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: path.path)
        }
        let zip = scratch.appending(path: "runtime-\(status).zip")
        let ditto = Process()
        ditto.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        ditto.arguments = ["-c", "-k", stage.path, zip.path]
        try ditto.run()
        ditto.waitUntilExit()
        let size = try FileManager.default.attributesOfItem(atPath: zip.path)[.size] as! Int64
        return (zip, .init(file: zip.lastPathComponent, sha256: try RuntimeTools.sha256(of: zip), size: size))
    }

    func release(_ entry: RuntimeManifest.Archive, version: String = "1") -> BackendConfig.Release {
        let manifest = RuntimeManifest(version: version, base: scratch.absoluteString, tools: [:],
                                       archives: [RuntimeManifest.machine: entry])
        return .init(resources: scratch, shippedProject: scratch, runtime: scratch.appending(path: "runtime"),
                     uvCache: scratch.appending(path: "cache"), manifest: manifest)
    }

    @Test func aVerifiedZipBecomesTheToolsFolder() async throws {
        defer { try? FileManager.default.removeItem(at: scratch) }
        let (zip, entry) = try archive()
        let release = release(entry)
        #expect(!RuntimeTools.ready(release))
        try await RuntimeTools.install(release, from: zip, progress: { _ in }, verifying: {})
        #expect(RuntimeTools.ready(release))
        #expect(FileManager.default.fileExists(atPath: release.runtime.appending(path: "licenses/LICENSES").path))
        // Nothing of the download is left behind.
        let left = try FileManager.default.contentsOfDirectory(atPath: release.runtime.path).sorted()
        #expect(left == ["bin", "licenses"])
        // A new app version with newer tools wants them installed again.
        #expect(!RuntimeTools.ready(self.release(entry, version: "2")))
    }

    @Test func aZipThatDoesNotMatchTheManifestIsNeverUnpacked() async throws {
        defer { try? FileManager.default.removeItem(at: scratch) }
        var (zip, entry) = try archive()
        entry.sha256 = String(repeating: "0", count: 64)
        let release = release(entry)
        await #expect(throws: RuntimeTools.Failure.checksum) {
            try await RuntimeTools.install(release, from: zip, progress: { _ in }, verifying: {})
        }
        #expect(!FileManager.default.fileExists(atPath: release.bin.path))
        #expect(try FileManager.default.contentsOfDirectory(atPath: release.runtime.path).isEmpty)
    }

    @Test func aToolThatDoesNotRunKeepsTheOldSet() async throws {
        defer { try? FileManager.default.removeItem(at: scratch) }
        let good = try archive()
        try await RuntimeTools.install(release(good.entry), from: good.zip, progress: { _ in }, verifying: {})
        let bad = try archive(status: 3)
        let release = release(bad.entry, version: "2")
        await #expect(throws: RuntimeTools.Failure.broken("deno")) {
            try await RuntimeTools.install(release, from: bad.zip, progress: { _ in }, verifying: {})
        }
        #expect(RuntimeTools.ready(self.release(good.entry)))  // version 1 still there, whole
    }

    @Test func aMissingFileIsANetworkFailure() async throws {
        defer { try? FileManager.default.removeItem(at: scratch) }
        let (_, entry) = try archive()
        let release = release(entry)
        await #expect(throws: RuntimeTools.Failure.self) {
            try await RuntimeTools.install(release, from: scratch.appending(path: "nowhere.zip"), progress: { _ in }, verifying: {})
        }
        #expect(!RuntimeTools.ready(release))
    }

    @MainActor
    @Test func aReleaseWithoutItsToolsWaitsForTheAssistant() async throws {
        defer { try? FileManager.default.removeItem(at: scratch) }
        let (_, entry) = try archive()
        let calls = scratch.appending(path: "uv-calls")
        let uv = scratch.appending(path: "uv")
        try "#!/bin/sh\necho \"$@\" >> \(calls.path)\nexit 7\n".write(to: uv, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: uv.path)
        let config = BackendConfig(port: Int.random(in: 20000...29999), projectRoot: nil, uv: uv, environment: [:],
                                   logFile: scratch.appending(path: "log"), release: release(entry))
        let backend = BackendController(config: config)
        await backend.start()
        #expect(backend.state == .needsSetup)
        #expect(!FileManager.default.fileExists(atPath: calls.path))  // uv was not run: nothing downloaded
    }
}
