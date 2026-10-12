import AppKit
import WebKit

/// One long-lived web view showing the existing web UI in embedded mode (`?embedded=1`) for the
/// screens not yet ported to SwiftUI. It is created once and kept, so a half-filled track
/// picker survives a trip to another screen and back -- exactly as in the browser.
@MainActor
public final class WebBridge: NSObject {
    public let webView: DroppingWebView
    /// The page moved to another screen on its own ("Stüdyo'da aç", "Kuyruğu aç").
    public var onRoute: ((String) -> Void)?
    /// A link was dropped anywhere on the page.
    public var onDrop: ((URL) -> Void)?

    private let origin: URL
    private var loaded = false
    private var route = "inspect"
    /// The page has installed `window.vd` and said so. Until then calls wait here: a script
    /// run while the page is still loading dies with the document it ran in, so a link handed
    /// to the app at launch would be lost.
    private var pageReady = false
    private var queued: [(expression: String, value: String)] = []

    public init(port: Int) {
        origin = URL(string: "http://127.0.0.1:\(port)")!
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        webView = DroppingWebView(frame: .zero, configuration: configuration)
        super.init()
        configuration.userContentController.add(WeakMessageHandler(self), name: "vd")
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.setValue(false, forKey: "drawsBackground")  // no white flash before the page paints
        webView.onDrop = { [weak self] url in self?.onDrop?(url) }
    }

    /// Load the page on `route`: the native window's current screen, so a screen chosen before
    /// the page existed is not lost.
    public func load(route: String) {
        guard !loaded else { return }
        loaded = true
        pageReady = false
        self.route = route
        var components = URLComponents(url: origin, resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "embedded", value: "1"), URLQueryItem(name: "route", value: route)]
        webView.load(URLRequest(url: components.url!))
    }

    /// Leave the page: its event stream closes with it, so the server can stop at once.
    public func unload() {
        guard loaded else { return }
        loaded = false
        pageReady = false
        queued = []
        webView.stopLoading()
        webView.loadHTMLString("", baseURL: nil)
    }

    public func reload(route: String) {
        unload()
        load(route: route)
    }

    public func navigate(_ route: String) {
        self.route = route
        call("vd.navigate(value)", value: route)
    }

    public func inspect(_ url: URL) {
        call("vd.inspect(value)", value: url.absoluteString)
    }

    /// The value is passed as an argument, never spliced into the script.
    private func call(_ expression: String, value: String) {
        guard pageReady else {
            // Only the last navigation matters; every link handed in does.
            if expression.hasPrefix("vd.navigate") { queued.removeAll { $0.expression.hasPrefix("vd.navigate") } }
            queued.append((expression, value))
            return
        }
        webView.callAsyncJavaScript("window.vd && \(expression)", arguments: ["value": value], in: nil, in: .page) { _ in }
    }

    fileprivate func received(_ body: Any) {
        guard let message = body as? [String: Any] else { return }
        switch message["type"] as? String {
        case "ready":
            pageReady = true
            let waiting = queued
            queued = []
            waiting.forEach { call($0.expression, value: $0.value) }
        case "route":
            if let route = message["route"] as? String { onRoute?(route) }
        default:
            break
        }
    }

    fileprivate func isOurs(_ url: URL?) -> Bool {
        guard let url else { return false }
        return url.scheme == origin.scheme && url.host() == origin.host() && url.port == origin.port
    }
}

extension WebBridge: WKNavigationDelegate, WKUIDelegate {
    /// Only the app's own pages load here (plus the blank page used to unload). A link the user
    /// clicks to anywhere else opens in the default browser; nothing else ever leaves.
    public func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction) async -> WKNavigationActionPolicy {
        let url = action.request.url
        if isOurs(url) || url?.absoluteString == "about:blank" { return .allow }
        if action.targetFrame?.isMainFrame != false, action.navigationType == .linkActivated,
           let url, ["http", "https"].contains(url.scheme ?? "") {
            NSWorkspace.shared.open(url)
        }
        return .cancel
    }

    public func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                        for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if action.navigationType == .linkActivated, let url = action.request.url,
           ["http", "https"].contains(url.scheme ?? "") {
            NSWorkspace.shared.open(url)
        }
        return nil
    }

    /// WebKit's content process can be killed (memory pressure, a crash): show the page again
    /// instead of an empty window.
    public func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        guard loaded else { return }
        let current = route
        loaded = false
        load(route: current)
    }
}

/// WKUserContentController keeps its handlers alive; this keeps the bridge out of that cycle.
private final class WeakMessageHandler: NSObject, WKScriptMessageHandler {
    weak var bridge: WebBridge?
    init(_ bridge: WebBridge) { self.bridge = bridge }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        let body = message.body
        MainActor.assumeIsolated { bridge?.received(body) }
    }
}

/// A web view that takes a dropped web link (or .webloc) for the app to inspect, wherever on
/// the page it lands; everything else (text into a field, files) is the page's business.
public final class DroppingWebView: WKWebView {
    var onDrop: ((URL) -> Void)?

    private func droppedLink(_ info: NSDraggingInfo) -> URL? {
        let urls = info.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: nil) as? [URL] ?? []
        for url in urls {
            if case .inspect(let target)? = IncomingURL.parse(url) { return target }
        }
        return nil
    }

    public override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        droppedLink(sender) != nil ? .copy : super.draggingEntered(sender)
    }

    public override func draggingUpdated(_ sender: NSDraggingInfo) -> NSDragOperation {
        droppedLink(sender) != nil ? .copy : super.draggingUpdated(sender)
    }

    public override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        guard let url = droppedLink(sender) else { return super.performDragOperation(sender) }
        onDrop?(url)
        return true
    }
}
