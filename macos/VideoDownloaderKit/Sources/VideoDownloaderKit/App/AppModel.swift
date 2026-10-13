import AppKit
import Observation
import UserNotifications

/// The app's state: the backend, the screen on show, the live job list (for the sidebar and
/// Dock badges and the notifications), and links handed in from outside.
@MainActor
@Observable
public final class AppModel {
    public enum Connection: Sendable { case connecting, open, reconnecting }

    public let backend: BackendController
    public private(set) var jobs: [String: Job] = [:]
    /// False until the first snapshot: "loading", not "no downloads yet".
    public private(set) var jobsLoaded = false
    public private(set) var connection: Connection = .connecting
    /// The backend runs on recorded answers (tests): no remote image is loaded then. Unknown
    /// (nil) counts as yes: an answer that came late must not let a test fetch i.ytimg.com.
    public private(set) var fixtureMode: Bool?
    public var remoteImages: Bool { fixtureMode == false }
    /// A link the opt-in clipboard watcher saw being copied, offered for inspection.
    public var clipboardOffer: String?
    public let inspector: Inspector
    public let librarian: Librarian
    public let studio: Studio
    public let preview = PreviewPlayer()
    /// A finished download could not be added to the library (its file is on disk).
    public var catalogueFailed = false
    /// Per-user conveniences; a file in the data folder under tests (never Berk's preferences).
    @ObservationIgnored public let store: LocalStore
    public private(set) var activeCount = 0 {
        didSet { NSApp?.dockTile.badgeLabel = activeCount > 0 ? String(activeCount) : nil }
    }

    /// The screen on show (every one of them is SwiftUI since N7).
    public var route: Route = .inspect

    public let preferences: Preferences
    /// Menu bar item, Dock icon, start at login.
    public let shell: Shell
    @ObservationIgnored private var events: Task<Void, Never>?
    @ObservationIgnored private var pending: [IncomingURL] = []
    @ObservationIgnored private var askedForNotifications = false
    @ObservationIgnored private let notificationActions = NotificationActions()

    public init(config: BackendConfig = .resolve()) {
        let backend = BackendController(config: config)
        self.backend = backend
        let store = LocalStore.forEnvironment(config.environment)
        self.store = store
        inspector = Inspector(client: { backend.client }, rules: QuickRules(store: store))
        librarian = Librarian(client: { backend.client }, store: store)
        studio = Studio(client: { backend.client })
        preferences = Preferences(client: { backend.client })
        shell = Shell(store: store)
        backend.onLost = { [weak self] in self?.backendLost() }
        notificationActions.model = self
    }

    public var isReady: Bool {
        if case .ready = backend.state { return true }
        return false
    }

    public func start() async {
        await backend.start()
        guard isReady else { return }
        // What arrived while the backend was starting (a link from Safari, a screen) is handled
        // now that it answers.
        let waiting = pending
        pending = []
        fixtureMode = await backend.client.health(timeout: 10)?.fixtureMode
        // Not for a test bundle run without an app (the center needs one).
        if Bundle.main.bundleIdentifier != nil { notificationActions.install() }
        listen()
        waiting.forEach(handle)
    }

    /// One fresh attempt, never two: the controller is reset, then started once.
    public func retry() async {
        events?.cancel()
        await backend.reset()
        await start()
    }

    public func shutdown() async {
        events?.cancel()
        preview.pause()
        await backend.stop()
    }

    /// The backend went away after being ready: nothing it reported can be trusted any more.
    private func backendLost() {
        events?.cancel()
        jobs = [:]
        jobsLoaded = false
        connection = .connecting
        activeCount = 0
    }

    /// Newest first, as the web queue lists them.
    public var jobList: [Job] {
        jobs.values.sorted { ($0.createdAt ?? 0, $0.id) > ($1.createdAt ?? 0, $1.id) }
    }

    public func handle(_ incoming: IncomingURL) {
        guard isReady else {
            pending.append(incoming)
            return
        }
        NSApp?.activate()
        switch incoming {
        case .inspect(let url):
            route = .inspect
            inspector.run(url.absoluteString)
        case .show(let target):
            if let target { route = target }
        }
    }

    /// "Stüdyo'da aç" from Kütüphane.
    public func openInStudio(item id: String) {
        route = .studio
        studio.open(item: id)
    }

    public func inspectClipboard() {
        guard let text = NSPasteboard.general.string(forType: .string)?.trimmingCharacters(in: .whitespacesAndNewlines),
              let url = URL(string: text), let incoming = IncomingURL.parse(url) else { return }
        handle(incoming)
    }

    // ---- live jobs --------------------------------------------------------------------------

    private func listen() {
        events?.cancel()
        let stream = EventStream(client: backend.client)
        events = Task { [weak self] in
            for await event in stream.events() {
                guard let self else { return }
                await self.apply(event)
            }
        }
    }

    func apply(_ event: ServerEvent) async {
        switch event {
        case .snapshot(let all):
            jobs = Dictionary(all.map { ($0.id, $0) }, uniquingKeysWith: { $1 })
            jobsLoaded = true
            connection = .open
            // A (re)connect may have missed `library` events: ask the library again.
            librarian.changed()
        case .disconnected:
            connection = .reconnecting
        case .job(let job):
            let previous = jobs[job.id]
            jobs[job.id] = job
            await notify(previous: previous, current: job)
        case .removed(let id):
            jobs[id] = nil
        case .clipboard(let url):
            clipboardOffer = url
        case .library:
            librarian.changed()
        case .libraryError:
            catalogueFailed = true
        case .other:
            break  // the embedded page shows these
        }
        activeCount = jobs.values.filter { $0.status.isActive }.count
    }

    private func notify(previous: Job?, current: Job) async {
        // Cheap first: only a real transition while the app is in the background asks further.
        guard JobNotification.for(previous: previous, current: current, appIsActive: NSApp?.isActive ?? true, enabled: true) != nil,
              let settings = try? await backend.client.settings(),
              let note = JobNotification.for(previous: previous, current: current, appIsActive: NSApp?.isActive ?? true,
                                             enabled: settings.notifications) else { return }
        let center = UNUserNotificationCenter.current()
        if !askedForNotifications {
            askedForNotifications = true
            _ = try? await center.requestAuthorization(options: [.alert, .sound])
        }
        let content = UNMutableNotificationContent()
        switch note {
        case .done(let title):
            content.title = L("notify.done")
            content.body = title
            content.categoryIdentifier = NotificationActions.done
        case .failed(let title):
            content.title = L("notify.failed")
            content.body = title
            content.categoryIdentifier = NotificationActions.failed
        }
        content.userInfo = ["job": current.id]
        try? await center.add(UNNotificationRequest(identifier: current.id + current.status.rawValue, content: content, trigger: nil))
    }
}
