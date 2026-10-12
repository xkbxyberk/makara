import SwiftUI

/// The main window: the backend's state until it is ready, then the split view.
public struct RootView: View {
    @Bindable var model: AppModel

    public init(model: AppModel) { self.model = model }

    public var body: some View {
        switch model.backend.state {
        case .ready:
            MainSplitView(model: model)
        case .failed(let failure):
            BackendFailureView(failure: failure, log: model.backend.logTail(),
                               logFile: model.backend.config.logFile) {
                Task { await model.retry() }
            }
        case .syncing:
            StartingView(text: L("backend.syncing"))
        case .idle, .starting, .stopped:
            StartingView(text: L("backend.starting"))
        }
    }
}

struct MainSplitView: View {
    @Bindable var model: AppModel

    var body: some View {
        NavigationSplitView {
            List(selection: Binding(get: { model.route }, set: { if let next = $0 { model.route = next } })) {
                Section(L("nav.section.media")) {
                    ForEach(Route.media) { route in row(route) }
                }
                Section(L("nav.section.app")) {
                    ForEach(Route.app) { route in row(route) }
                }
            }
            .navigationSplitViewColumnWidth(min: 180, ideal: 210, max: 280)
        } detail: {
            WebScreen(bridge: model.web)
                .navigationTitle(model.route.title)
        }
    }

    private func row(_ route: Route) -> some View {
        Label(route.title, systemImage: route.symbol)
            .badge(route == .download ? model.activeCount : 0)
            .tag(route)
            .accessibilityIdentifier("sidebar.\(route.rawValue)")
    }
}

/// The embedded web page for screens not yet ported to SwiftUI.
public struct WebScreen: NSViewRepresentable {
    let bridge: WebBridge

    public init(bridge: WebBridge) { self.bridge = bridge }

    public func makeNSView(context: Context) -> DroppingWebView { bridge.webView }
    public func updateNSView(_ view: DroppingWebView, context: Context) {}
}

struct StartingView: View {
    let text: String

    var body: some View {
        VStack(spacing: 12) {
            ProgressView().controlSize(.large)
            Text(text).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityIdentifier("backend.starting")
    }
}

struct BackendFailureView: View {
    let failure: BackendFailure
    let log: String
    let logFile: URL
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            ContentUnavailableView {
                Label(L("backend.failed.title"), systemImage: "exclamationmark.triangle")
            } description: {
                Text(Self.reason(failure))
            } actions: {
                HStack {
                    Button(L("backend.retry"), action: retry)
                        .buttonStyle(.borderedProminent)
                        .keyboardShortcut(.defaultAction)
                    Button(L("backend.showLog")) { NSWorkspace.shared.activateFileViewerSelecting([logFile]) }
                }
            }
            if !log.isEmpty {
                ScrollView {
                    Text(log)
                        .font(.system(.caption, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                }
                .frame(maxWidth: 640, maxHeight: 180)
                .background(.quaternary.opacity(0.5), in: .rect(cornerRadius: 8))
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityIdentifier("backend.failed")
    }

    static func reason(_ failure: BackendFailure) -> String {
        switch failure {
        case .noProject: L("backend.reason.noProject")
        case .noPython: L("backend.reason.noPython")
        case .syncFailed(let code): L("backend.reason.syncFailed", Int(code))
        case .exited(let code): L("backend.reason.exited", Int(code))
        case .timedOut(let seconds): L("backend.reason.timedOut", seconds)
        case .portBusy(let port): L("backend.reason.portBusy", port)
        case .spawnFailed(let code): L("backend.reason.spawnFailed", Int(code))
        case .lost: L("backend.reason.lost")
        }
    }
}

/// ⌘, -- the settings screen, shown in the Mac's own Settings window.
public struct SettingsView: View {
    let model: AppModel

    public init(model: AppModel) { self.model = model }

    public var body: some View {
        Group {
            if model.isReady {
                WebScreen(bridge: model.settingsWeb)
                    .onAppear { model.showSettings() }
                    .onDisappear { model.hideSettings() }  // no event stream for a closed window
            } else {
                ContentUnavailableView(L("settings.unavailable"), systemImage: "gearshape")
            }
        }
        .frame(minWidth: 620, idealWidth: 680, minHeight: 520, idealHeight: 620)
    }
}

/// Menus: the sidebar toggle, ⌘1…⌘5 for the screens, and inspecting the copied link.
public struct AppCommands: Commands {
    let model: AppModel

    public init(model: AppModel) { self.model = model }

    public var body: some Commands {
        SidebarCommands()
        CommandGroup(after: .newItem) {
            Button(L("menu.inspectClipboard")) { model.inspectClipboard() }
                .keyboardShortcut("v", modifiers: [.command, .shift])
                .disabled(!model.isReady)
        }
        CommandMenu(L("menu.go")) {
            ForEach(Route.allCases) { route in
                Button(route.title) { model.route = route }
                    .keyboardShortcut(KeyEquivalent(route.shortcut), modifiers: .command)
                    .disabled(!model.isReady)
            }
        }
    }
}
