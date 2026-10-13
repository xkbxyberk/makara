import Foundation
import Observation

/// Small per-user conveniences (the remembered quick choices, the library's grid or list): the
/// app's preferences, or a JSON file in the data folder when one is given -- tests run this same
/// bundle with their own `VD_DATA_DIR` and must never read or change Berk's.
/// `@unchecked`: UserDefaults is documented as thread-safe, and the file is written atomically.
public struct LocalStore: @unchecked Sendable {
    private let defaults: UserDefaults?
    private let folder: URL?

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.folder = nil
    }

    public init(folder: URL) {
        self.defaults = nil
        self.folder = folder
    }

    /// Berk's preferences, unless the environment names a data folder (tests, development).
    public static func forEnvironment(_ environment: [String: String]) -> LocalStore {
        guard let dir = environment["VD_DATA_DIR"], !dir.isEmpty else { return LocalStore() }
        return LocalStore(folder: URL(fileURLWithPath: dir))
    }

    private func file(_ key: String) -> URL? { folder?.appending(path: "native-\(key).json") }

    public func data(_ key: String) -> Data? {
        if let file = file(key) { return try? Data(contentsOf: file) }
        return defaults?.data(forKey: key)
    }

    public func set(_ data: Data, _ key: String) {
        if let file = file(key) {
            try? FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? data.write(to: file, options: .atomic)
        } else {
            defaults?.set(data, forKey: key)
        }
    }

    public func string(_ key: String) -> String? { data(key).map { String(decoding: $0, as: UTF8.self) } }
    public func set(_ value: String, _ key: String) { set(Data(value.utf8), key) }
}

/// The last quick choice per site ("1080p · MKV" on youtube.com), so the next video from that
/// site opens with the closest choice preselected (the native twin of `quickRule.ts`). A
/// convenience: a missing or damaged entry is simply no rule.
public struct QuickRules: Sendable {
    public static let key = "vd-quick-rules"
    /// Hosts that are the same site for this purpose: one remembered choice for all of them.
    static let aliases = ["youtu.be": "youtube.com", "music.youtube.com": "youtube.com"]

    let store: LocalStore

    public init(store: LocalStore = LocalStore()) { self.store = store }

    public static func site(of url: String) -> String? {
        guard var host = URLComponents(string: url)?.host?.lowercased(), !host.isEmpty else { return nil }
        for prefix in ["www.", "m."] where host.hasPrefix(prefix) {
            host.removeFirst(prefix.count)
            break
        }
        return aliases[host] ?? host
    }

    private func all() -> [String: QuickRule] {
        guard let data = store.data(Self.key),
              let raw = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return [:] }
        // Entry by entry: one damaged rule must not cost the others. A bare string or number is
        // not a JSON object, and serialising it would raise (not throw): check first.
        return raw.compactMapValues { value in
            guard JSONSerialization.isValidJSONObject(value) else { return nil }
            return (try? JSONSerialization.data(withJSONObject: value)).flatMap { try? JSON.decoder.decode(QuickRule.self, from: $0) }
        }
    }

    public func load(for url: String) -> QuickRule? {
        guard let site = Self.site(of: url), let rule = all()[site], rule.isValid else { return nil }
        return rule
    }

    public func save(_ rule: QuickRule, for url: String) {
        guard let site = Self.site(of: url) else { return }
        var rules = all()
        rules[site] = rule
        if let data = try? JSONEncoder().encode(rules) { store.set(data, Self.key) }
    }
}

/// İncele's state, kept by the app model so a result survives a trip to another screen and a
/// link handed in from outside (Safari, the Dock, the clipboard) lands here.
@MainActor
@Observable
public final class Inspector {
    public enum Phase: Equatable {
        case empty
        case loading(String)
        case failed(APIError, url: String)
        /// `remembered`: the inspect was asked with this site's last quick choice.
        case ready(InspectResult, remembered: Bool)
    }

    public var url = ""
    public internal(set) var phase: Phase = .empty {
        didSet {
            // The panel's state belongs to this result, here rather than in the view: going to
            // İndirmeler and back must keep the tracks, the template and "Kuyruğa eklendi".
            if case .ready(.video(let model), let remembered) = phase {
                if planner?.model.inspectId != model.inspectId { planner = DownloadPlanner(model: model, remembered: remembered) }
            } else {
                planner = nil
            }
        }
    }
    /// The download panel of the video on show.
    public private(set) var planner: DownloadPlanner?

    @ObservationIgnored private let client: () -> APIClient
    @ObservationIgnored public let rules: QuickRules
    @ObservationIgnored private var ticket = 0
    @ObservationIgnored private var task: Task<Void, Never>?

    public init(client: @escaping () -> APIClient, rules: QuickRules = QuickRules()) {
        self.client = client
        self.rules = rules
    }

    public var isLoading: Bool {
        if case .loading = phase { return true }
        return false
    }

    /// Inspect `target`; a newer inspect always wins over a slower older one.
    public func run(_ target: String) {
        let trimmed = target.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        ticket += 1
        let mine = ticket
        url = trimmed
        phase = .loading(trimmed)
        let rule = rules.load(for: trimmed)
        let client = client()
        task?.cancel()
        task = Task { [weak self] in
            let outcome: Phase
            do {
                outcome = .ready(try await client.inspect(trimmed, rule: rule), remembered: rule != nil)
            } catch {
                if Task.isCancelled { return }
                outcome = .failed(APIError.from(error), url: trimmed)
            }
            guard let self, self.ticket == mine else { return }
            self.phase = outcome
        }
    }

    public func retry() {
        if case .failed(_, let failed) = phase { run(failed) }
    }

}
