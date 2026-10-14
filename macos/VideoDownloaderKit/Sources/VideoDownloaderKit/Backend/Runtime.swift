import CryptoKit
import Darwin
import Foundation

/// The tools a release installs into `runtime/bin` (PLAN P8): one zip per architecture, made by
/// `scripts/runtime/build_runtime.sh`, pinned here by SHA-256 (`runtime-manifest.json`).
public struct RuntimeManifest: Codable, Sendable, Equatable {
    public struct Archive: Codable, Sendable, Equatable {
        public var file: String
        public var sha256: String
        public var size: Int64
    }

    public var version: String
    /// Where the zips are published (a GitHub release), ending in "/".
    public var base: String
    public var tools: [String: String]
    public var archives: [String: Archive]

    public static func bundled() -> RuntimeManifest? {
        guard let url = Bundle.module.url(forResource: "runtime-manifest", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(RuntimeManifest.self, from: data)
    }

    /// This Mac's processor, as the archives are named.
    public static var machine: String {
        var info = utsname()
        uname(&info)
        let raw = withUnsafeBytes(of: &info.machine) { String(decoding: $0.prefix { $0 != 0 }, as: UTF8.self) }
        return raw == "arm64" ? "arm64" : "x86_64"
    }

    public var archiveForThisMac: Archive? { archives[Self.machine] }
}

/// Installing and checking `runtime/bin`. No UI here (see `RuntimeSetup`).
public enum RuntimeTools {
    /// Every tool, with the argument that makes it print its version and exit 0.
    static let tools: [(name: String, versionArgument: String)] = [
        ("ffmpeg", "-version"), ("ffprobe", "-version"), ("deno", "--version"), ("aria2c", "--version"),
    ]
    static let stamp = ".version"

    public enum Failure: Error, Equatable {
        case network(String)
        case checksum
        case space(needed: Int64)
        case broken(String)
    }

    /// Installed, and from this manifest's version (a new app version may bring newer tools).
    public static func ready(_ release: BackendConfig.Release, fileManager: FileManager = .default) -> Bool {
        guard let manifest = release.manifest,
              let version = try? String(contentsOf: release.bin.appending(path: stamp), encoding: .utf8),
              version == manifest.version else { return false }
        return tools.allSatisfy { fileManager.isExecutableFile(atPath: release.bin.appending(path: $0.name).path) }
    }

    /// Room for the zip, its contents and Python with its packages.
    public static func spaceNeeded(_ archive: RuntimeManifest.Archive) -> Int64 { archive.size * 4 + 400_000_000 }

    /// The zip from `source`, checked against the manifest, unpacked, each tool run once, then
    /// swapped in for `runtime/bin` in one move. Nothing unverified is ever left runnable.
    public static func install(_ release: BackendConfig.Release, from source: URL,
                               progress: @escaping @Sendable (Double) -> Void,
                               verifying: @escaping @Sendable () -> Void) async throws {
        guard let manifest = release.manifest, let archive = manifest.archiveForThisMac else {
            throw Failure.broken("no archive for \(RuntimeManifest.machine)")
        }
        let fileManager = FileManager.default
        try fileManager.createDirectory(at: release.runtime, withIntermediateDirectories: true)
        let free = (try? release.runtime.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]))?
            .volumeAvailableCapacityForImportantUsage ?? .max
        if free < spaceNeeded(archive) { throw Failure.space(needed: spaceNeeded(archive)) }

        let work = release.runtime.appending(path: "install-\(UUID().uuidString)")
        try fileManager.createDirectory(at: work, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: work) }
        let zip = work.appending(path: archive.file)
        try await download(source, to: zip, expected: archive.size, progress: progress)

        verifying()
        guard try sha256(of: zip) == archive.sha256.lowercased() else { throw Failure.checksum }
        let unpacked = work.appending(path: "unpacked")
        guard await run(URL(fileURLWithPath: "/usr/bin/ditto"), ["-x", "-k", zip.path, unpacked.path]) == 0 else {
            throw Failure.broken("ditto")
        }
        let bin = unpacked.appending(path: "bin")
        for tool in tools {
            let path = bin.appending(path: tool.name)
            guard fileManager.isExecutableFile(atPath: path.path),
                  await run(path, [tool.versionArgument]) == 0 else { throw Failure.broken(tool.name) }
        }
        try manifest.version.write(to: bin.appending(path: stamp), atomically: true, encoding: .utf8)

        // Swap: the old folder moves aside first, so a failure leaves one complete set.
        let old = release.runtime.appending(path: "bin.old")
        try? fileManager.removeItem(at: old)
        if fileManager.fileExists(atPath: release.bin.path) { try fileManager.moveItem(at: release.bin, to: old) }
        try fileManager.moveItem(at: bin, to: release.bin)
        try? fileManager.removeItem(at: old)
        let licenses = release.runtime.appending(path: "licenses")
        try? fileManager.removeItem(at: licenses)
        try? fileManager.moveItem(at: unpacked, to: licenses)  // LICENSES/, SOURCES.md
    }

    static func download(_ source: URL, to destination: URL, expected: Int64,
                         progress: @escaping @Sendable (Double) -> Void) async throws {
        // Ephemeral: no cache, no cookies, nothing of this left in the app's caches.
        let session = URLSession(configuration: .ephemeral)
        defer { session.finishTasksAndInvalidate() }
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            let task = session.downloadTask(with: source) { temporary, response, error in
                if let error {
                    continuation.resume(throwing: Failure.network(error.localizedDescription))
                    return
                }
                if let http = response as? HTTPURLResponse, http.statusCode != 200 {
                    continuation.resume(throwing: Failure.network("HTTP \(http.statusCode)"))
                    return
                }
                guard let temporary else {
                    continuation.resume(throwing: Failure.network("no file"))
                    return
                }
                do {
                    try FileManager.default.moveItem(at: temporary, to: destination)
                    continuation.resume()
                } catch {
                    continuation.resume(throwing: Failure.network(error.localizedDescription))
                }
            }
            let observation = task.progress.observe(\.completedUnitCount) { value, _ in
                let total = value.totalUnitCount > 0 ? value.totalUnitCount : expected
                progress(total > 0 ? min(Double(value.completedUnitCount) / Double(total), 1) : 0)
            }
            // Kept alive by the task's own lifetime.
            objc_setAssociatedObject(task, &observationKey, observation, .OBJC_ASSOCIATION_RETAIN)
            task.resume()
        }
    }

    static func sha256(of file: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: file)
        defer { try? handle.close() }
        var hasher = SHA256()
        while let chunk = try handle.read(upToCount: 4 << 20), !chunk.isEmpty { hasher.update(data: chunk) }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    /// Exit status of a fixed argument list (never a shell), output discarded; -1 if it could
    /// not start or took longer than a minute.
    static func run(_ executable: URL, _ arguments: [String]) async -> Int32 {
        await withCheckedContinuation { continuation in
            let process = Process()
            process.executableURL = executable
            process.arguments = arguments
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            process.terminationHandler = { continuation.resume(returning: $0.terminationStatus) }
            do { try process.run() } catch {
                process.terminationHandler = nil
                continuation.resume(returning: -1)
                return
            }
            DispatchQueue.global().asyncAfter(deadline: .now() + 60) { if process.isRunning { process.terminate() } }
        }
    }
}

nonisolated(unsafe) private var observationKey: UInt8 = 0
