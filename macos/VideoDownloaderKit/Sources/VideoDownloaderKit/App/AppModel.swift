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
    public private(set) var activeCount = 0 {
        didSet { NSApp?.dockTile.badgeLabel = activeCount > 0 ? String(activeCount) : nil }
    }

    /// The screen on show. Setting it moves the web page too, unless the page itself moved.
    public var route: Route = .inspect {
        didSet {
            if route != oldValue, !followingPage, let page = route.pageRoute { web.navigate(page) }
        }
    }

    @ObservationIgnored public let web: WebBridge
    @ObservationIgnored public let settingsWeb: WebBridge
    @ObservationIgnored private var followingPage = false
    @ObservationIgnored private var events: Task<Void, Never>?
    @ObservationIgnored private var pending: [IncomingURL] = []
    @ObservationIgnored private var askedForNotifications = false

    public init(config: BackendConfig = .resolve()) {
        let backend = BackendController(config: config)
        self.backend = backend
        inspector = Inspector(client: { backend.client }, rules: QuickRules.forEnvironment(config.environment))
        web = WebBridge(port: config.port)
        settingsWeb = WebBridge(port: config.port)
        web.onRoute = { [weak self] raw in self?.pageMoved(to: raw) }
        backend.onLost = { [weak self] in self?.backendLost() }
        web.onDrop = { [weak self] url in self?.handle(.inspect(url)) }
        settingsWeb.onDrop = { [weak self] url in self?.handle(.inspect(url)) }
    }

    public var isReady: Bool {
        if case .ready = backend.state { return true }
        return false
    }

    public func start() async {
        await backend.start()
        guard isReady else { return }
        // A screen asked for before the page existed becomes the page's first screen; links
        // wait in the bridge until the page says it is ready.
        let waiting = pending
        pending = []
        for case .show(let target?) in waiting { route = target }
        // The page is only seen on the screens not ported yet; it waits on an idle one.
        web.load(route: route.pageRoute ?? Route.inspect.rawValue)
        fixtureMode = await backend.client.health(timeout: 10)?.fixtureMode
        listen()
        waiting.forEach(handle)
    }

    /// One fresh attempt, never two: the controller is reset, then started once.
    public func retry() async {
        events?.cancel()
        web.unload()
        await backend.reset()
        await start()
    }

    public func shutdown() async {
        events?.cancel()
        // The pages' own event streams close with them, so the server can stop at once.
        web.unload()
        settingsWeb.unload()
        await backend.stop()
    }

    public func showSettings() {
        settingsWeb.reload(route: "settings")
    }

    public func hideSettings() {
        settingsWeb.unload()
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

    public func inspectClipboard() {
        guard let text = NSPasteboard.general.string(forType: .string)?.trimmingCharacters(in: .whitespacesAndNewlines),
              let url = URL(string: text), let incoming = IncomingURL.parse(url) else { return }
        handle(incoming)
    }

    private func pageMoved(to raw: String) {
        // On a native screen the page is hidden and nobody uses it: what it reports is only its
        // own loading, which must not pull the window away from İndirmeler or Sistem.
        guard !route.isNative, let next = Route(rawValue: raw), next != route else { return }
        followingPage = true
        route = next
        followingPage = false
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
        case .library, .other:
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
        case .failed(let title):
            content.title = L("notify.failed")
            content.body = title
        }
        try? await center.add(UNNotificationRequest(identifier: current.id + current.status.rawValue, content: content, trigger: nil))
    }
}
