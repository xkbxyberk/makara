import QuickLook
import SwiftUI

/// Kütüphane: every finished download and Stüdyo output, as a grid or a list, with the item's
/// details in the window's inspector. Play opens the default player; nothing is deleted, only
/// moved to the Trash after a confirmation.
struct LibraryView: View {
    @Bindable var librarian: Librarian
    let client: APIClient
    let openInStudio: (String) -> Void
    /// Quick Look of the selected item's file (space bar, or the menu).
    @State private var preview: URL?
    /// The grid takes the keyboard focus when an item is clicked, so the space bar reaches it.
    @FocusState private var gridFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            filters
            Divider()
            notices
            content
        }
        .toolbar { toolbar }
        .navigationSubtitle(summary)
        .searchable(text: $librarian.query.search, placement: .toolbar, prompt: Text(L("library.search")))
        // The column's width belongs to a container that is always there: set inside the `if`, it
        // came and went with the selection, and the split view's sizes fed back into each other
        // until AppKit aborted the app (constraint passes exceeded).
        .inspector(isPresented: Binding(get: { librarian.selection != nil }, set: { if !$0 { librarian.selection = nil } })) {
            Group {
                if let item = librarian.selectedItem {
                    ItemInspector(item: item, client: client, actions: actions)
                } else {
                    Color.clear
                }
            }
            .inspectorColumnWidth(min: 260, ideal: 300, max: 400)
        }
        .confirmationDialog(L("library.trashTitle"), isPresented: Binding(get: { librarian.confirming != nil },
                                                                         set: { if !$0 { librarian.confirming = nil } }),
                            titleVisibility: .visible, presenting: librarian.confirming) { item in
            Button(L("library.confirmTrash"), role: .destructive) { Task { await librarian.trash(item) } }
            // Return cancels, as on the web page (its dialog focuses "Vazgeç").
            Button(L("library.cancel"), role: .cancel) { librarian.confirming = nil }
                .keyboardShortcut(.defaultAction)
        } message: { item in
            // The item by name: a right-click can ask about an item other than the one selected.
            Text("“\(item.title ?? "–")”\n\n" + (item.files.count == 1 ? L("libraryNative.trashBodyOne")
                                                                  : L("libraryNative.trashBodyMany", item.files.count)))
        }
        .confirmationDialog(L("libraryNative.forgetTitle"), isPresented: Binding(get: { librarian.forgetting != nil },
                                                                                 set: { if !$0 { librarian.forgetting = nil } }),
                            titleVisibility: .visible, presenting: librarian.forgetting) { item in
            Button(L("libraryNative.forget"), role: .destructive) { Task { await librarian.forget(item) } }
            Button(L("library.cancel"), role: .cancel) { librarian.forgetting = nil }
                .keyboardShortcut(.defaultAction)
        } message: { item in
            Text("“\(item.title ?? "–")”\n\n" + L("libraryNative.forgetBody"))
        }
        .confirmationDialog(L("libraryNative.forgetAllTitle", librarian.page?.facets.missing ?? 0), isPresented: $librarian.forgettingAll,
                            titleVisibility: .visible) {
            Button(L("libraryNative.forgetAllConfirm"), role: .destructive) { Task { await librarian.forgetAllMissing() } }
            Button(L("library.cancel"), role: .cancel) {}
                .keyboardShortcut(.defaultAction)
        } message: {
            Text(L("libraryNative.forgetAllBody"))
        }
        .quickLookPreview($preview)
        // A moment after typing in the search field, at once for any other change (as the web page).
        .task(id: librarian.trigger) {
            if !librarian.query.search.isEmpty { try? await Task.sleep(for: .milliseconds(150)) }
            guard !Task.isCancelled else { return }
            await librarian.load()
        }
        .onKeyPress(.space) {
            guard let item = librarian.selectedItem, !item.isMissing else { return .ignored }
            preview = preview == nil ? URL(fileURLWithPath: item.primaryPath) : nil
            return .handled
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("library")
    }

    // ---- the bars ---------------------------------------------------------------------------

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItem {
            Picker(L("library.view"), selection: $librarian.layout) {
                // Icon-only in the toolbar, which then names a segment after its symbol
                // ("Izgara Görüntüsü"): say the words explicitly.
                Label(L("library.grid"), systemImage: "square.grid.2x2").accessibilityLabel(L("library.grid"))
                    .tag(Librarian.Layout.grid)
                Label(L("library.list"), systemImage: "list.bullet").accessibilityLabel(L("library.list"))
                    .tag(Librarian.Layout.list)
            }
            .pickerStyle(.segmented)
            .help(L("library.view"))
            .accessibilityIdentifier("library.layout")
        }
        ToolbarItem {
            // The same label throughout: swapping it for a spinner resized the toolbar item, and
            // that fed back into the split view's sizes until AppKit aborted the app. The
            // progress shows in the content instead.
            Button {
                Task { await librarian.runScan() }
            } label: {
                Label(L("library.scan"), systemImage: "arrow.clockwise")
            }
            .help(L("library.scanHelp"))
            .disabled(librarian.scan == .running)
            .accessibilityIdentifier("library.scan")
        }
    }

    /// The filters, scrolling sideways when the window is narrow. A bar wider than the window
    /// pushed the whole split view off screen; choosing a narrower bar by width (ViewThatFits)
    /// fed back into the split view's minimum size until AppKit aborted the app.
    private var filters: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            filterRow(labels: true)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
        }
        .scrollBounceBehavior(.basedOnSize)
        // Only as tall as the bar: a sideways scroll view otherwise asks for every free point of
        // height, and fought the grid/list for it.
        .fixedSize(horizontal: false, vertical: true)
    }

    private func filterRow(labels: Bool) -> some View {
        HStack(spacing: 12) {
            Group {
                Picker(L("library.siteLabel"), selection: $librarian.query.site) {
                    Text(L("library.allSites")).tag("")
                    ForEach(librarian.page?.facets.sites ?? [], id: \.self) { Text($0).tag($0) }
                }
                if librarian.query.category.isEmpty {  // a shelf already is one kind
                    Picker(L("library.kindLabel"), selection: $librarian.query.kind) {
                        Text(L("library.kind.all")).tag("")
                        Text(L("library.kind.video")).tag("video")
                        Text(L("library.kind.audio")).tag("audio")
                    }
                }
                Picker(L("library.sortLabel"), selection: $librarian.query.sort) {
                    ForEach(["added", "uploaded", "title", "size", "duration"], id: \.self) { Text(L("library.sort.\($0)")).tag($0) }
                }
            }
            .labelsShown(labels)
            .fixedSize()
            Toggle(L("library.onlyMissing"), isOn: Binding(get: { librarian.query.status == "missing" },
                                                          set: { librarian.query.status = $0 ? "missing" : "" }))
                .toggleStyle(.checkbox)
                .fixedSize()
            if let missing = librarian.page?.facets.missing, missing > 0 {
                Button(L("libraryNative.forgetAll", missing), systemImage: "minus.circle") { librarian.forgettingAll = true }
                    .help(L("libraryNative.forgetAllHelp"))
                    .fixedSize()
                    .accessibilityIdentifier("library.forgetAll")
            }
            Spacer(minLength: 0)
        }
    }

    /// "3 öğe · 1.2 GB · 1 eksik", under the window title.
    private var summary: String {
        guard let facets = librarian.page?.facets else { return "" }
        return facets.missing > 0 ? L("library.summaryMissing", facets.count, Format.bytes(facets.totalSize), facets.missing)
                                  : L("library.summary", facets.count, Format.bytes(facets.totalSize))
    }

    /// One line each, at most two. Not `NoticeRow`: its text is fixed to its own height, which
    /// in a split view column (outside a scroll view) depends on the width, and the two fed back
    /// into the column's minimum size until AppKit aborted the app.
    @ViewBuilder private var notices: some View {
        if librarian.scan == .running {
            noticeLine {
                ProgressView().controlSize(.small)
                Text(L("library.scanning")).foregroundStyle(.secondary)
            }
        }
        if case .done(let result) = librarian.scan {
            noticeLine {
                Image(systemName: "info.circle").foregroundStyle(.secondary)
                Text(L("library.scanResult", result.checked, result.repaired, result.restored, result.missing))
                    .foregroundStyle(.secondary)
            }
            .accessibilityIdentifier("library.scanResult")
        }
        if let removed = librarian.forgotten {
            noticeLine {
                Image(systemName: "checkmark.circle").foregroundStyle(.secondary)
                Text(L("libraryNative.forgetAllResult", removed)).foregroundStyle(.secondary)
            }
        }
        if let code = librarian.actionError {
            noticeLine {
                Image(systemName: "xmark.octagon.fill").foregroundStyle(.red)
                Text(localizedIfPresent("error.\(code).title") ?? code).foregroundStyle(.red)
            }
        }
    }

    private func noticeLine<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        HStack(spacing: 8) { content() }
            .lineLimit(2)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16)
            .padding(.vertical, 6)
            .accessibilityElement(children: .combine)
    }

    @ViewBuilder private var content: some View {
        switch librarian.phase {
        case .loading:
            ProgressView(L("library.loading")).frame(maxWidth: .infinity, maxHeight: .infinity)
        case .failed(let error):
            ErrorStateView(error: error) { Task { await librarian.load() } }
        case .ready(let page) where page.items.isEmpty:
            Group {
                if librarian.query.isFiltered {
                    ContentUnavailableView(L("library.noMatchTitle"), systemImage: "magnifyingglass",
                                           description: Text(L("library.noMatchBody")))
                } else if !librarian.query.category.isEmpty {
                    ContentUnavailableView(L("library.shelfEmpty.\(librarian.query.category)"),
                                           systemImage: "books.vertical",
                                           description: Text(L("library.shelfEmptyBody.\(librarian.query.category)")))
                } else {
                    ContentUnavailableView(L("library.emptyTitle"), systemImage: "books.vertical",
                                           description: Text(L("library.emptyBody")))
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("library.empty")
        case .ready(let page):
            switch librarian.layout {
            case .grid: grid(page.items)
            case .list: list(page.items)
            }
        }
    }

    // ---- grid and list ----------------------------------------------------------------------

    private func grid(_ items: [LibraryItem]) -> some View {
        ScrollView {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 200, maximum: 280), spacing: 14)], spacing: 14) {
                ForEach(items) { item in
                    ItemCard(item: item, thumbnail: thumbnail(item), selected: librarian.selection == item.id)
                        .onTapGesture(count: 2) { if !item.isMissing { run { try await $0.open(item: item.id) } } }
                        .onTapGesture {
                            librarian.selection = librarian.selection == item.id ? nil : item.id
                            gridFocused = true
                        }
                        .contextMenu { menu(item) }
                }
            }
            .padding(16)
        }
        .focusable()
        .focusEffectDisabled()
        .focused($gridFocused)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("library.grid")
    }

    private func list(_ items: [LibraryItem]) -> some View {
        Table(items, selection: $librarian.selection) {
            TableColumn(L("table.name")) { item in
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(item.title ?? "–").lineLimit(1)
                        if item.isMissing { MissingBadge() }
                    }
                    if let channel = item.channel { Text(channel).font(.caption).foregroundStyle(.secondary) }
                }
            }
            .width(min: 220, ideal: 360)
            TableColumn(L("library.siteLabel")) { Text($0.site ?? "–").foregroundStyle(.secondary) }
                .width(min: 70, ideal: 100)
            TableColumn(L("library.sort.uploaded")) { Text(Format.uploadDate($0.uploadDate)).foregroundStyle(.secondary) }
                .width(min: 90, ideal: 110)
            TableColumn(L("table.duration")) { Text(Format.duration($0.duration)).monospacedDigit() }
                .width(min: 60, ideal: 70)
            TableColumn(L("table.size")) { Text(Format.bytes($0.size)).monospacedDigit() }
                .width(min: 60, ideal: 80)
        }
        .contextMenu(forSelectionType: LibraryItem.ID.self) { ids in
            if let id = ids.first, let item = items.first(where: { $0.id == id }) { menu(item) }
        } primaryAction: { ids in
            if let id = ids.first, let item = items.first(where: { $0.id == id }), !item.isMissing {
                run { try await $0.open(item: item.id) }
            }
        }
        .accessibilityIdentifier("library.list")
    }

    // ---- actions ----------------------------------------------------------------------------

    private func thumbnail(_ item: LibraryItem) -> String? {
        item.thumbnail == nil ? nil : client.thumbnailURL(item: item.id).absoluteString
    }

    private func run(_ action: @escaping @Sendable (APIClient) async throws -> Void) {
        Task { await librarian.perform(action) }
    }

    private var actions: ItemInspector.Actions {
        ItemInspector.Actions(
            play: { item in run { try await $0.open(item: item.id) } },
            reveal: { item in run { try await $0.reveal(item: item.id) } },
            quickLook: { item in preview = URL(fileURLWithPath: item.primaryPath) },
            studio: { item in openInStudio(item.id) },
            trash: { item in
                // The item asked about is the one on show in the inspector, too.
                librarian.selection = item.id
                librarian.confirming = item
            },
            forget: { item in
                librarian.selection = item.id
                librarian.forgetting = item
            })
    }

    @ViewBuilder private func menu(_ item: LibraryItem) -> some View {
        let missing = item.isMissing
        Button(L("library.play")) { actions.play(item) }.disabled(missing)
        Button(L("libraryNative.quickLook")) { actions.quickLook(item) }.disabled(missing)
        Button(L("library.reveal")) { actions.reveal(item) }.disabled(missing)
        Button(L("library.openInStudio")) { actions.studio(item) }.disabled(missing)
        if let source = item.sourceUrl {
            Button(L("queue.copyLink")) {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(source, forType: .string)
            }
        }
        Divider()
        if missing {
            Button(L("libraryNative.forget"), role: .destructive) { actions.forget(item) }
        } else {
            Button(L("library.trash"), role: .destructive) { actions.trash(item) }
        }
    }
}

struct MissingBadge: View {
    var body: some View {
        Badge(text: L("library.missing"), tone: .warn).help(L("library.missingHelp"))
    }
}

struct ModeBadge: View {
    let mode: String?

    var body: some View {
        if let mode {
            Badge(text: localizedIfPresent("mode.\(mode)") ?? mode)
                .help(localizedIfPresent("download.modeHelp.\(mode)") ?? "")
        }
    }
}

struct ItemCard: View {
    let item: LibraryItem
    let thumbnail: String?
    let selected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            RemoteImage(url: thumbnail, systemImage: item.kind == "audio" ? "music.note" : "film")
                .frame(maxWidth: .infinity)
                .aspectRatio(16 / 9, contentMode: .fit)
                .clipShape(.rect(cornerRadius: 6))
            Text(item.title ?? "–").font(.body.weight(.medium)).lineLimit(2, reservesSpace: true)
            Text([item.channel, Format.duration(item.duration), Format.bytes(item.size)].compactMap { $0 }.joined(separator: " · "))
                .font(.caption).foregroundStyle(.secondary).lineLimit(1)
            HStack(spacing: 4) {
                ModeBadge(mode: item.mode)
                if item.isMissing { MissingBadge() }
            }
        }
        .padding(8)
        .background(selected ? Color.accentColor.opacity(0.12) : .clear, in: .rect(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(selected ? Color.accentColor : .clear, lineWidth: 2))
        .contentShape(.rect)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(selected ? [.isSelected, .isButton] : .isButton)
        .accessibilityIdentifier("library.item")
    }
}

struct ItemInspector: View {
    struct Actions {
        let play: (LibraryItem) -> Void
        let reveal: (LibraryItem) -> Void
        let quickLook: (LibraryItem) -> Void
        let studio: (LibraryItem) -> Void
        let trash: (LibraryItem) -> Void
        let forget: (LibraryItem) -> Void
    }

    let item: LibraryItem
    let client: APIClient
    let actions: Actions

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                RemoteImage(url: item.thumbnail == nil ? nil : client.thumbnailURL(item: item.id).absoluteString,
                            systemImage: item.kind == "audio" ? "music.note" : "film")
                    .clipShape(.rect(cornerRadius: 8))
                Text(item.title ?? "–").font(.headline).textSelection(.enabled)
                    .accessibilityIdentifier("inspector.title")
                if let channel = item.channel { Text(channel).foregroundStyle(.secondary) }
                HStack(spacing: 4) {
                    ModeBadge(mode: item.mode)
                    if item.isMissing { MissingBadge() }
                }
                buttons
                details
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("inspector")
    }

    private var buttons: some View {
        let missing = item.isMissing
        return VStack(alignment: .leading, spacing: 6) {
            if missing {
                // The file is gone: the only thing left to do is to drop the record.
                Text(L("library.missingHelp")).font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Button(role: .destructive) { actions.forget(item) } label: {
                    Label(L("libraryNative.forget"), systemImage: "minus.circle").frame(maxWidth: .infinity, alignment: .leading)
                }
                .accessibilityIdentifier("inspector.forget")
            }
            Button { actions.play(item) } label: {
                Label(L("library.play"), systemImage: "play.fill").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .help(L("library.playHelp"))
            .disabled(missing)
            Group {
                Button { actions.quickLook(item) } label: { Label(L("libraryNative.quickLook"), systemImage: "eye").frame(maxWidth: .infinity, alignment: .leading) }
                Button { actions.reveal(item) } label: { Label(L("library.reveal"), systemImage: "folder").frame(maxWidth: .infinity, alignment: .leading) }
                Button { actions.studio(item) } label: { Label(L("library.openInStudio"), systemImage: "scissors").frame(maxWidth: .infinity, alignment: .leading) }
                Button(role: .destructive) { actions.trash(item) } label: {
                    Label(L("library.trash"), systemImage: "trash").frame(maxWidth: .infinity, alignment: .leading)
                }
                .accessibilityIdentifier("inspector.trash")
            }
            .disabled(missing)
        }
    }

    private var details: some View {
        Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 6) {
            if let video = item.tracks.video.first {
                row(L("library.video"), [video.height.map { "\($0)p" }, video.codec?.uppercased()].compactMap { $0 }.joined(separator: " · "))
            }
            row(L("library.audioTracks"), Self.languages(item.tracks.audio))
            row(L("library.subtitleTracks"), Self.languages(item.tracks.subtitle))
            GridRow(alignment: .top) {
                Text(L("library.files")).foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(item.files, id: \.path) { file in
                        Text(file.path).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            if let source = item.sourceUrl {
                GridRow(alignment: .top) {
                    Text(L("library.source")).foregroundStyle(.secondary)
                    Text(source).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            row(L("library.added"), Date(timeIntervalSince1970: item.addedAt)
                .formatted(Date.FormatStyle(date: .abbreviated, time: .shortened).locale(Format.turkish)))
        }
        .font(.callout)
    }

    private func row(_ label: String, _ value: String) -> some View {
        GridRow(alignment: .top) {
            Text(label).foregroundStyle(.secondary)
            Text(value.isEmpty ? L("library.noTracks") : value)
        }
    }

    /// The languages of a set of tracks, each once, in Turkish ("İngilizce, Türkçe"), or "–".
    static func languages(_ tracks: [LibraryTrack]) -> String {
        var seen: [String] = []
        for code in tracks.compactMap(\.language) where !seen.contains(code) { seen.append(code) }
        return seen.isEmpty ? L("library.noTracks") : seen.map(Format.language).joined(separator: ", ")
    }
}
