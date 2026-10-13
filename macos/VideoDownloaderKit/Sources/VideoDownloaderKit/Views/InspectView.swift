import SwiftUI
import UniformTypeIdentifiers

extension EnvironmentValues {
    /// False against a fixture-mode backend: tests never touch the network, and a recorded
    /// YouTube answer points its thumbnails at i.ytimg.com.
    @Entry var remoteImages = true
}

/// A picture from the site (a thumbnail), or a quiet placeholder. Only this Mac's own test
/// server is asked when remote images are off.
struct RemoteImage: View {
    let url: String?
    /// Shown when there is no picture (a film or a note, for a library item).
    var systemImage = "photo"
    @Environment(\.remoteImages) private var remoteImages

    var body: some View {
        if let url, let target = URL(string: url), allowed(target) {
            AsyncImage(url: target) { phase in
                if let image = phase.image {
                    image.resizable().aspectRatio(contentMode: .fit)
                } else {
                    placeholder
                }
            }
        } else {
            placeholder
        }
    }

    private func allowed(_ target: URL) -> Bool {
        guard let scheme = target.scheme?.lowercased(), scheme == "https" || scheme == "http" else { return false }
        return remoteImages || ["127.0.0.1", "localhost"].contains(target.host() ?? "")
    }

    private var placeholder: some View {
        Rectangle().fill(.quaternary).aspectRatio(16 / 9, contentMode: .fit)
            .overlay(Image(systemName: systemImage).font(.title).foregroundStyle(.tertiary))
    }
}

/// A titled box, the web page's `<Panel>`.
struct Panel<Content: View>: View {
    let title: String
    var count: Int? = nil
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(title).font(.headline)
                if let count { Text("\(count)").foregroundStyle(.secondary).monospacedDigit() }
            }
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.background.secondary, in: .rect(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(.separator.opacity(0.6)))
    }
}

/// İncele: paste or drop a link, see everything the video offers, download it.
struct InspectView: View {
    @Bindable var inspector: Inspector
    let client: APIClient
    let openQueue: () -> Void
    var openLibrary: (String) -> Void = { _ in }
    @FocusState private var fieldFocused: Bool
    @FocusState private var pageFocused: Bool

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                urlBar
                content
            }
            .padding(20)
            .frame(maxWidth: 1100)
            .frame(maxWidth: .infinity)
            // Clicking anywhere outside the field takes the focus here, so ⌘V reaches this
            // screen (paste commands only go to the focused view). No ring: it is the page.
            .contentShape(.rect)
            .focusable()
            .focusEffectDisabled()
            .focused($pageFocused)
            .onTapGesture { pageFocused = true }
        }
        // ⌘V anywhere (outside a text field, which handles its own paste) inspects the link.
        .onPasteCommand(of: [.url, .plainText]) { providers in paste(providers) }
        .dropDestination(for: URL.self) { urls, _ in
            guard let url = urls.first(where: { ["http", "https"].contains($0.scheme?.lowercased() ?? "") }) else { return false }
            inspector.run(url.absoluteString)
            return true
        }
        // A container: without .contain its identifier would replace every child's.
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("inspect")
    }

    private var urlBar: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "link").foregroundStyle(.secondary)
                    TextField(L("inspect.urlLabel"), text: $inspector.url, prompt: Text(L("inspect.urlPlaceholder")))
                        .textFieldStyle(.plain)
                        .focused($fieldFocused)
                        .onSubmit { inspector.run(inspector.url) }
                        .accessibilityIdentifier("inspect.url")
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(.background, in: .rect(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(.separator))
                Button {
                    inspector.run(inspector.url)
                } label: {
                    if inspector.isLoading {
                        ProgressView().controlSize(.small)
                    } else {
                        Label(L("inspect.submit"), systemImage: "magnifyingglass")
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(inspector.isLoading)
                .accessibilityIdentifier("inspect.submit")
            }
            Text(L("inspect.pasteHint")).font(.caption).foregroundStyle(.secondary)
        }
    }

    @ViewBuilder private var content: some View {
        switch inspector.phase {
        case .empty:
            Panel(title: L("inspect.title")) {
                ContentUnavailableView {
                    Label(L("inspect.emptyTitle"), systemImage: "doc.on.clipboard")
                } description: {
                    Text(L("inspect.emptyBody"))
                }
            }
        case .loading:
            Panel(title: L("inspect.title")) {
                VStack(spacing: 10) {
                    ProgressView().controlSize(.large)
                    Text(L("inspect.loadingTitle")).font(.headline)
                    Text(L("inspect.loadingBody")).foregroundStyle(.secondary).multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 30)
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("inspect.loading")
            }
        case .failed(let error, _):
            Panel(title: L("inspect.title")) {
                ErrorStateView(error: error) { inspector.retry() }
            }
        case .ready(.playlist(let playlist), _):
            PlaylistView(model: playlist) { inspector.run($0) }
        case .ready(.video(let model), _):
            if let planner = inspector.planner {
                VideoResult(model: model, planner: planner, client: client, rules: inspector.rules,
                            openQueue: openQueue, openLibrary: openLibrary) { inspector.run(model.sourceUrl) }
                    .id(model.inspectId)  // a new inspect starts fresh disclosure states
            }
        }
    }

    private func paste(_ providers: [NSItemProvider]) {
        guard !fieldFocused else { return }
        for provider in providers where provider.canLoadObject(ofClass: NSString.self) {
            _ = provider.loadObject(ofClass: NSString.self) { text, _ in
                guard let text = (text as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
                      text.lowercased().hasPrefix("http://") || text.lowercased().hasPrefix("https://") else { return }
                Task { @MainActor in inspector.run(text) }
            }
            return
        }
    }
}

// ---- a video -------------------------------------------------------------------------------

struct VideoResult: View {
    let model: VideoModel
    let planner: DownloadPlanner
    let client: APIClient
    let rules: QuickRules
    let openQueue: () -> Void
    let openLibrary: (String) -> Void
    let reinspect: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let hit = model.inLibrary?.first {
                // P6a: said before a second download, never in the way of one.
                HStack(spacing: 10) {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(L("inspect.inLibrary")).font(.body.weight(.medium))
                        Text(L("inspect.inLibraryBody", hit.mode.flatMap { localizedIfPresent("mode.\($0)") } ?? "",
                               hit.addedAt.map { Date(timeIntervalSince1970: $0).formatted(.relative(presentation: .named)) } ?? ""))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(L("inspect.showInLibrary")) { openLibrary(hit.id) }
                }
                .padding(10)
                .background(.green.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("inspect.inLibrary")
            }
            ForEach(model.warnings, id: \.self) { code in
                Label(localizedIfPresent("inspectWarning.\(code)") ?? code, systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(code.hasPrefix("DRM") ? .red : .orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Metadata(media: model.media)
            DownloadPanelView(planner: planner, client: client, rules: rules, openQueue: openQueue, reinspect: reinspect)
            FormatTable(title: L("inspect.videoFormats"), formats: model.videoFormats)
            if !model.muxedFormats.isEmpty {
                FormatTable(title: L("inspect.muxedFormats"), formats: model.muxedFormats)
            }
            AudioGroups(groups: model.audioLanguages)
            SubtitlesPanel(subtitles: model.subtitles)
            if !model.chapters.isEmpty {
                Panel(title: L("inspect.chapters"), count: model.chapters.count) {
                    ForEach(Array(model.chapters.enumerated()), id: \.offset) { _, chapter in
                        HStack(spacing: 12) {
                            Text(Format.duration(chapter.startTime)).monospacedDigit().foregroundStyle(.secondary)
                                .frame(width: 64, alignment: .trailing)
                            Text(chapter.title ?? "–")
                        }
                    }
                }
            }
            if !model.heatmap.isEmpty { Heatmap(points: model.heatmap) }
            Panel(title: L("inspect.thumbnails"), count: model.thumbnails.count) {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
                    ForEach(Array(model.thumbnails.prefix(12).enumerated()), id: \.offset) { _, thumb in
                        VStack(spacing: 4) {
                            RemoteImage(url: thumb.url).clipShape(.rect(cornerRadius: 6))
                            Text(thumb.width.flatMap { w in thumb.height.map { "\(w)×\($0)" } } ?? (thumb.id ?? ""))
                                .font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            Panel(title: L("inspect.commands")) {
                Text(L("inspect.commandSuggested")).foregroundStyle(.secondary)
                CommandText(command: model.commands.suggested)
                Text(L("inspect.commandInspect")).foregroundStyle(.secondary)
                CommandText(command: model.commands.inspect)
            }
        }
    }
}

/// A command to copy, shown as it will be pasted.
struct CommandText: View {
    let command: String

    var body: some View {
        HStack(alignment: .top) {
            Text(command)
                .font(.system(.callout, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
            CopyButton(value: command)
        }
        .padding(8)
        .background(.quaternary.opacity(0.5), in: .rect(cornerRadius: 6))
    }
}

struct Metadata: View {
    let media: MediaMeta
    @State private var open = false

    var body: some View {
        Panel(title: L("inspect.metadata")) {
            HStack(alignment: .top, spacing: 16) {
                RemoteImage(url: media.thumbnail)
                    .frame(width: 240)
                    .clipShape(.rect(cornerRadius: 8))
                VStack(alignment: .leading, spacing: 6) {
                    Text(media.title ?? "–").font(.title3.weight(.semibold)).textSelection(.enabled)
                        .accessibilityIdentifier("inspect.title")
                    HStack(spacing: 12) {
                        if let channel = media.channel { Text(channel) }
                        Text(Format.uploadDate(media.uploadDate))
                        Text(Format.duration(media.duration)).monospacedDigit()
                        if let views = media.viewCount, views > 0 { Text(L("inspect.views", Format.count(views))) }
                        if let extractor = media.extractor {
                            Text(extractor).font(.system(.callout, design: .monospaced)).foregroundStyle(.tertiary)
                        }
                    }
                    .foregroundStyle(.secondary)
                    if let description = media.description, !description.isEmpty {
                        Text(description)
                            .lineLimit(open ? nil : 3)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                        Button(open ? L("app.showLess") : L("app.showMore")) { open.toggle() }
                            .buttonStyle(.link)
                    }
                }
            }
        }
    }
}

// ---- tables --------------------------------------------------------------------------------

/// A size, with "estimated" or "manifest" explained on hover when it is not exact.
struct SizeText: View {
    let bytes: Double?
    let kind: SizeKind
    let unreliable: Bool

    var body: some View {
        let text = Format.size(bytes, kind)
        if kind == .exact || bytes == nil {
            Text(text)
        } else {
            Term(text, help: L(kind == .partial ? "term.partialSize.body" : unreliable ? "term.manifest.body" : "term.approxSize.body"))
        }
    }
}

struct CodecText: View {
    let label: String?

    var body: some View {
        if let label {
            if let help = localizedIfPresent("codec.\(label)") { Term(label, help: help) } else { Text(label) }
        } else {
            Text("–")
        }
    }
}

struct FormatBadges: View {
    let drm: String
    let aiUpscaled: Bool
    let drc: Bool
    var muxed = false

    var body: some View {
        if drm != "none" { Badge(text: L("term.drm.label"), tone: .danger).help(L("term.drm.body")) }
        if aiUpscaled { Badge(text: L("term.aiUpscaled.label"), tone: .warn).help(L("term.aiUpscaled.body")) }
        if drc { Badge(text: L("term.drc.label")).help(L("term.drc.body")) }
        if muxed { Badge(text: L("term.muxed.label"), tone: .accent).help(L("term.muxed.body")) }
    }
}

struct FormatTable: View {
    let title: String
    let formats: [VideoFormat]

    var body: some View {
        Panel(title: title, count: formats.count) {
            if formats.isEmpty {
                Text(L("inspect.noVideoFormats")).foregroundStyle(.secondary)
            } else {
                Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 6) {
                    GridRow {
                        Term(term: "format")
                        Text(L("table.resolution"))
                        Term(term: "fps").gridColumnAlignment(.trailing)
                        Term(term: "codec")
                        Term(term: "hdr")
                        Term(term: "bitrate").gridColumnAlignment(.trailing)
                        Term(term: "container")
                        Text(L("table.size")).gridColumnAlignment(.trailing)
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    Divider()
                    ForEach(formats) { format in
                        GridRow {
                            HStack(spacing: 4) {
                                Text(format.formatId).font(.system(.callout, design: .monospaced))
                                FormatBadges(drm: format.drm, aiUpscaled: format.aiUpscaled, drc: format.drc,
                                             muxed: format.hasAudio == true)
                            }
                            Text(format.resolution ?? "–")
                            Text(format.fps.map { "\(Int($0.rounded()))" } ?? "–").monospacedDigit()
                            HStack(spacing: 0) {
                                CodecText(label: format.vcodecLabel)
                                if format.hasAudio == true, let audio = format.acodecLabel {
                                    Text(" + ")
                                    CodecText(label: audio)
                                }
                            }
                            Text(format.dynamicRange ?? "–")
                                .foregroundStyle(format.dynamicRange == "SDR" ? .secondary : .primary)
                            Text(Format.bitrate(format.tbr)).monospacedDigit()
                            HStack(spacing: 0) {
                                Text(format.ext ?? "–")
                                if format.isManifest {
                                    Text(" · ")
                                    Term(term: "manifest")
                                }
                            }
                            .foregroundStyle(.secondary)
                            SizeText(bytes: format.filesize, kind: format.filesizeKind, unreliable: format.filesizeUnreliable)
                                .monospacedDigit()
                        }
                        .font(.callout)
                        // One element per row: read as a row, and a far smaller tree to walk.
                        .accessibilityElement(children: .combine)
                    }
                }
            }
        }
    }
}

struct AudioGroups: View {
    let groups: [AudioLanguageGroup]
    @State private var open: String?

    var body: some View {
        Panel(title: L("inspect.audioTracks"), count: groups.count) {
            if groups.isEmpty {
                Text(L("inspect.noAudioFormats")).foregroundStyle(.secondary)
            }
            ForEach(groups) { group in
                DisclosureGroup(isExpanded: Binding(get: { open == group.id }, set: { open = $0 ? group.id : nil })) {
                    Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 6) {
                        GridRow {
                            Term(term: "format")
                            Term(term: "codec")
                            Term(term: "bitrate").gridColumnAlignment(.trailing)
                            Term(term: "channels").gridColumnAlignment(.trailing)
                            Term(term: "sampleRate").gridColumnAlignment(.trailing)
                            Text(L("table.note"))
                            Text(L("table.size")).gridColumnAlignment(.trailing)
                        }
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                        ForEach(group.tracks) { track in
                            GridRow {
                                HStack(spacing: 4) {
                                    Text(track.formatId).font(.system(.callout, design: .monospaced))
                                    FormatBadges(drm: track.drm, aiUpscaled: track.aiUpscaled, drc: track.drc)
                                }
                                CodecText(label: track.acodecLabel)
                                Text(Format.bitrate(track.abr ?? track.tbr)).monospacedDigit()
                                Text(track.channels.map(String.init) ?? "–").monospacedDigit()
                                Text(Format.sampleRate(track.asr)).monospacedDigit()
                                Text(track.formatNote ?? "–").foregroundStyle(.secondary)
                                SizeText(bytes: track.filesize, kind: track.filesizeKind, unreliable: track.filesizeUnreliable)
                                    .monospacedDigit()
                            }
                            .font(.callout)
                            .accessibilityElement(children: .combine)
                        }
                    }
                    .padding(.top, 6)
                } label: {
                    HStack(spacing: 8) {
                        Text(Format.language(group.language)).font(.body.weight(.semibold))
                        RoleBadge(role: group.role)
                        Text(group.language ?? "—").font(.system(.callout, design: .monospaced)).foregroundStyle(.tertiary)
                        Spacer()
                        Text("\(group.tracks.count)").foregroundStyle(.secondary)
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("audio.\(group.id)")
            }
        }
        .onAppear { if open == nil { open = groups.first?.id } }
    }
}

struct RoleBadge: View {
    let role: String

    var body: some View {
        Badge(text: localizedIfPresent("role.\(role)") ?? role, tone: role == "original" ? .ok : .neutral)
            .help(localizedIfPresent("roleHelp.\(role)") ?? "")
    }
}

struct SubtitlesPanel: View {
    let subtitles: Subtitles
    @State private var showTranslated = false

    var body: some View {
        let total = subtitles.manual.count + subtitles.auto.count + subtitles.autoTranslated.count
        Panel(title: L("inspect.subtitles"), count: total) {
            if total == 0 {
                Text(L("inspect.noSubtitles")).foregroundStyle(.secondary)
            }
            if subtitles.hasLiveChat {
                Label(L("inspect.liveChat"), systemImage: "info.circle").foregroundStyle(.secondary)
            }
            if !subtitles.manual.isEmpty {
                group(L("inspect.subManual"), help: L("inspect.subManualHelp"), rows: subtitles.manual)
            }
            if !subtitles.auto.isEmpty {
                group(L("inspect.subAuto"), help: L("inspect.subAutoHelp"), rows: subtitles.auto)
            }
            if !subtitles.autoTranslated.isEmpty {
                DisclosureGroup(isExpanded: $showTranslated) {
                    SubtitleRows(rows: subtitles.autoTranslated)
                } label: {
                    HStack {
                        Term(L("inspect.subAutoTranslated"), help: L("inspect.subAutoTranslatedHelp")).font(.body.weight(.semibold))
                        Spacer()
                        Text(showTranslated ? L("inspect.subTranslatedHide") : L("inspect.subTranslatedCount", subtitles.autoTranslated.count))
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private func group(_ title: String, help: String, rows: [SubtitleTrack]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Term(title, help: help).font(.body.weight(.semibold))
                Text("\(rows.count)").foregroundStyle(.secondary)
            }
            SubtitleRows(rows: rows)
        }
    }
}

struct SubtitleRows: View {
    let rows: [SubtitleTrack]

    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 4) {
            ForEach(rows) { row in
                GridRow {
                    HStack(spacing: 6) {
                        Text(Format.language(row.language))
                        Text(row.key).font(.system(.callout, design: .monospaced)).foregroundStyle(.tertiary)
                        if row.isOriginalTrack == true { Badge(text: L("inspect.subOriginalTrack"), tone: .ok) }
                        if row.shadowedByManual == true {
                            Image(systemName: "info.circle").foregroundStyle(.tertiary).help(L("inspect.subShadowed"))
                        }
                    }
                    HStack(spacing: 0) {
                        Text(row.name ?? "–")
                        if let source = row.sourceLanguage {
                            Text(" · " + L("inspect.subFrom", Format.language(source))).foregroundStyle(.tertiary)
                        }
                    }
                    .foregroundStyle(.secondary)
                    Text(row.exts.joined(separator: " ")).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
                }
                .font(.callout)
                .opacity(row.shadowedByManual == true ? 0.55 : 1)
                .accessibilityElement(children: .combine)
            }
        }
    }
}

struct Heatmap: View {
    let points: [HeatmapPoint]

    var body: some View {
        let peak = max(1, points.compactMap(\.value).max() ?? 1)
        Panel(title: L("inspect.heatmap")) {
            HStack(alignment: .bottom, spacing: 1) {
                ForEach(Array(points.enumerated()), id: \.offset) { _, point in
                    Rectangle()
                        .fill(Color.accentColor.opacity(0.7))
                        .frame(maxWidth: .infinity)
                        .frame(height: max(1, 60 * (point.value ?? 0) / peak))
                }
            }
            .frame(height: 60, alignment: .bottom)
            .accessibilityHidden(true)
            Text(L("inspect.heatmapHint")).font(.caption).foregroundStyle(.secondary)
        }
    }
}

// ---- a playlist ----------------------------------------------------------------------------

struct PlaylistView: View {
    let model: PlaylistModel
    let inspect: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label {
                VStack(alignment: .leading, spacing: 2) {
                    Text(L("inspect.playlistTitle")).font(.headline)
                    Text(L("inspect.playlistBody", model.entryCount))
                }
            } icon: {
                Image(systemName: "list.bullet.rectangle").foregroundStyle(.orange)
            }
            Panel(title: model.media.title ?? L("inspect.playlistTitle"), count: model.entries.count) {
                Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 6) {
                    ForEach(Array(model.entries.enumerated()), id: \.offset) { _, entry in
                        GridRow {
                            Text(entry.title ?? "–").lineLimit(1)
                            Text(Format.duration(entry.duration)).monospacedDigit().foregroundStyle(.secondary)
                                .gridColumnAlignment(.trailing)
                            if let url = entry.url {
                                Button(L("inspect.playlistInspectEntry")) { inspect(url) }.buttonStyle(.link)
                            } else {
                                Text("")
                            }
                        }
                    }
                }
            }
        }
    }
}
