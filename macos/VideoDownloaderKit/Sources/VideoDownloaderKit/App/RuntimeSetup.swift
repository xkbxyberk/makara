import Foundation
import Observation

/// The setup assistant's state (PLAN P8): the tools first (FFmpeg, Deno, aria2 in one zip),
/// then Python and its packages, which the backend's own `uv sync` installs.
@MainActor
@Observable
public final class RuntimeSetup {
    public enum Stage: Equatable, Sendable {
        case waiting
        case downloading(Double)
        case verifying
        case done
        case failed(RuntimeTools.Failure)
    }

    public private(set) var tools: Stage = .waiting
    /// Shown from the first time setup was needed in this launch until the app is ready.
    public private(set) var shown = false
    public private(set) var running = false

    public init() {}

    public func needed() { shown = true }

    /// How much the button promises: the zip plus roughly what uv fetches.
    public static func downloadSize(_ release: BackendConfig.Release) -> Int64? {
        release.manifest?.archiveForThisMac.map { $0.size + 45_000_000 }
    }

    /// Installs the tools, then starts the backend (whose first sync installs Python).
    public func install(_ release: BackendConfig.Release, then start: @escaping () async -> Void) async {
        guard !running else { return }
        running = true
        defer { running = false }
        if !RuntimeTools.ready(release) {
            guard let manifest = release.manifest, let archive = manifest.archiveForThisMac,
                  let source = URL(string: manifest.base + archive.file) else {
                tools = .failed(.broken("manifest"))
                return
            }
            tools = .downloading(0)
            do {
                try await RuntimeTools.install(
                    release, from: source,
                    progress: { fraction in Task { @MainActor in self.report(.downloading(fraction)) } },
                    verifying: { Task { @MainActor in self.report(.verifying) } })
            } catch let failure as RuntimeTools.Failure {
                tools = .failed(failure)
                return
            } catch {
                tools = .failed(.broken(error.localizedDescription))
                return
            }
        }
        tools = .done
        await start()
    }

    /// Progress arrives from URLSession's queue and may land after the step moved on: only a
    /// download in progress takes it.
    private func report(_ stage: Stage) {
        if case .downloading = tools { tools = stage }
    }
}
