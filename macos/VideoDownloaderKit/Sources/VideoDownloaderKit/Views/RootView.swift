import SwiftUI

/// The main window: the backend's state until it is ready, then the split view.
public struct RootView: View {
    @Bindable var model: AppModel

    public init(model: AppModel) { self.model = model }

    public var body: some View {
        switch model.backend.state {
        case .ready:
            MainSplitView(model: model)
        case .needsSetup:
            SetupView(model: model)
        // While the assistant's last step (Python) runs, it stays on screen.
        case .syncing where model.setup.shown, .starting where model.setup.shown:
            SetupView(model: model)
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
    @State private var libraryOpen = true

    var body: some View {
        NavigationSplitView {
            List(selection: Binding(get: { model.route }, set: { if let next = $0 { model.route = next } })) {
                Section(L("nav.section.media")) {
                    row(.inspect)
                    row(.download)
                    // The shelves sit under Kütüphane, which itself shows everything.
                    DisclosureGroup(isExpanded: $libraryOpen) {
                        ForEach(Route.shelves) { route in row(route) }
                    } label: {
                        row(.library)
                    }
                    row(.studio)
                }
                Section(L("nav.section.app")) {
                    ForEach(Route.app) { route in row(route) }
                }
            }
            .navigationSplitViewColumnWidth(min: 180, ideal: 210, max: 280)
            // The shelves' counts, kept current while another screen is shown.
            .task(id: model.librarian.version) {
                if model.route.libraryCategory == nil { await model.librarian.load() }
            }
        } detail: {
            detail
                .navigationTitle(model.route.title)
                .safeAreaInset(edge: .top, spacing: 0) {
                    VStack(spacing: 0) {
                        catalogueBanner
                        clipboardBanner
                    }
                }
                .environment(\.remoteImages, model.remoteImages)
        }
        .onChange(of: model.route, initial: true) {
            if let category = model.route.libraryCategory, model.librarian.query.category != category {
                model.librarian.query.category = category
            }
        }
    }

    /// Every screen is SwiftUI.
    @ViewBuilder private var detail: some View {
        switch model.route {
        case .inspect:
            InspectView(inspector: model.inspector, client: model.backend.client,
                        openQueue: { model.route = .download },
                        openLibrary: { id in
                            model.librarian.query = LibraryQuery()  // nothing filtered away
                            model.librarian.selection = id
                            model.route = .library
                        })
        case .download:
            QueueView(jobs: model.jobList, loaded: model.jobsLoaded, connection: model.connection,
                      client: model.backend.client)
        case .doctor:
            DoctorView(client: model.backend.client)
        case .library, .videos, .music, .edits:
            LibraryView(librarian: model.librarian, client: model.backend.client) { model.openInStudio(item: $0) }
        case .studio:
            StudioView(studio: model.studio, preview: model.preview, client: model.backend.client,
                       library: model.librarian.page?.items.filter { !$0.isMissing } ?? []) { model.route = .download }
                .task { if model.librarian.page == nil { await model.librarian.load() } }  // for "Kütüphaneden seç"
        }
    }

    /// A finished download could not be catalogued: say so on every screen (the file is safe).
    @ViewBuilder private var catalogueBanner: some View {
        if model.catalogueFailed {
            HStack(spacing: 10) {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.yellow)
                Text(L("library.catalogueFailed"))
                Spacer()
                Button(L("clipboard.dismiss")) { model.catalogueFailed = false }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(.bar)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("library.catalogueFailed")
        }
    }

    /// The opt-in clipboard watcher saw a link being copied: offer it, on every screen.
    @ViewBuilder private var clipboardBanner: some View {
        if let url = model.clipboardOffer {
            HStack(spacing: 10) {
                Image(systemName: "link").foregroundStyle(Color.accentColor)
                Text(L("clipboard.offer"))
                Text(url).font(.system(.callout, design: .monospaced)).lineLimit(1).truncationMode(.middle)
                Spacer()
                Button(L("clipboard.inspect")) {
                    model.clipboardOffer = nil
                    model.handle(.inspect(URL(string: url)!))
                }
                .buttonStyle(.borderedProminent)
                .disabled(URL(string: url) == nil)
                Button(L("clipboard.dismiss")) { model.clipboardOffer = nil }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(.bar)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("clipboard.offer")
        }
    }

    private func row(_ route: Route) -> some View {
        Label(route.title, systemImage: route.symbol)
            .badge(count(route))
            .tag(route)
            .accessibilityIdentifier("sidebar.\(route.rawValue)")
    }

    private func count(_ route: Route) -> Int {
        let facets = model.librarian.page?.facets
        switch route {
        case .download: return model.activeCount
        case .library: return facets?.count ?? 0
        default:
            guard let category = route.libraryCategory, !category.isEmpty else { return 0 }
            return facets?.categories?[category] ?? 0
        }
    }
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

/// ⌘, -- the Mac's own Settings window.
public struct SettingsView: View {
    let model: AppModel

    public init(model: AppModel) { self.model = model }

    public var body: some View {
        Group {
            if model.isReady {
                PreferencesForm(preferences: model.preferences, shell: model.shell)
            } else {
                Form {
                    ShellSection(shell: model.shell)
                    Section {
                        Label(L("settings.unavailable"), systemImage: "gearshape").foregroundStyle(.secondary)
                    }
                }
                .formStyle(.grouped)
            }
        }
        .frame(minWidth: 560, idealWidth: 620, minHeight: 480, idealHeight: 560)
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
