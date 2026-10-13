import AVKit
import SwiftUI
import UniformTypeIdentifiers

/// Stüdyo: a source, its preview stepped frame by frame, the pieces to keep chosen on a
/// filmstrip with two handles (snapped to the source's frames, or to its keyframes for a
/// lossless cut), and the operation's settings, the exact plan and the button in the inspector.
struct StudioView: View {
    @Bindable var studio: Studio
    let preview: PreviewPlayer
    let client: APIClient
    let library: [LibraryItem]
    let openQueue: () -> Void
    @FocusState private var focused: Bool

    var body: some View {
        content
            .toolbar { toolbar }
            .navigationSubtitle(studio.source?.name ?? "")
            .dropDestination(for: URL.self) { urls, _ in
                guard let file = urls.first(where: \.isFileURL) else { return false }
                studio.open(path: file.path)
                return true
            }
            .inspector(isPresented: .constant(studio.source != nil)) {
                Group {
                    if studio.source != nil {
                        StudioPanel(studio: studio, openQueue: openQueue)
                    } else {
                        Color.clear
                    }
                }
                .inspectorColumnWidth(min: 300, ideal: 340, max: 440)
            }
            .task(id: studio.bodyKey) {
                try? await Task.sleep(for: .milliseconds(200))
                guard !Task.isCancelled else { return }
                await studio.refreshPlan()
            }
            .onChange(of: studio.source) { _, source in
                if let source { preview.load(source, grid: studio.grid, client: client) }
            }
            // Leaving Stüdyo stops the sound: nothing would be left on screen to stop it with.
            .onDisappear { preview.pause() }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("studio")
    }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItem {
            Menu {
                Button(L("studio.chooseFile"), systemImage: "folder") { chooseFile() }
                if !library.isEmpty {
                    Divider()
                    Section(L("studio.fromLibrary")) {
                        ForEach(library.prefix(30)) { item in
                            Button(item.title ?? item.primaryPath) { studio.open(item: item.id) }
                        }
                    }
                }
            } label: {
                Label(L("studioNative.chooseSource"), systemImage: "film.stack")
            }
            .accessibilityIdentifier("studio.source")
        }
    }

    @ViewBuilder private var content: some View {
        switch studio.phase {
        case .empty:
            ContentUnavailableView {
                Label(L("studio.emptyTitle"), systemImage: "scissors")
            } description: {
                Text(L("studio.emptyBody"))
            } actions: {
                Button(L("studio.chooseFile")) { chooseFile() }.buttonStyle(.borderedProminent)
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("studio.empty")
        case .probing:
            ProgressView(L("studio.probing")).frame(maxWidth: .infinity, maxHeight: .infinity)
        case .failed(let error):
            ErrorStateView(error: error)
        case .ready(let source):
            editor(source)
        }
    }

    private func editor(_ source: StudioSource) -> some View {
        VStack(spacing: 0) {
            PreviewSurface(preview: preview, source: source)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            if source.hasMedia {
                Transport(studio: studio, preview: preview)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                Divider()
            }
            if studio.operation == .trim, source.hasMedia {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        TrimTimeline(studio: studio, preview: preview)
                            .frame(height: 92)
                        RangeEditor(studio: studio, preview: preview)
                        Pieces(studio: studio, preview: preview, chapters: source.chapters)
                    }
                    .padding(16)
                }
                .frame(height: 300)
            }
        }
        .focusable()
        .focusEffectDisabled()
        .focused($focused)
        .onTapGesture { focused = true }
        .onAppear { focused = true }
        .onKeyPress(phases: [.down, .repeat]) { press in keys(press) }
    }

    /// Space play/pause, ←/→ a frame, ⇧ a second, ⌥ the previous/next keyframe, I/O start/end.
    private func keys(_ press: KeyPress) -> KeyPress.Result {
        let second = max(1, Int((1 / studio.grid.unit).rounded()))
        switch press.key {
        case .space:
            guard press.phase == .down else { return .handled }
            preview.togglePlay(from: studio.current?.start)
        case .leftArrow, .rightArrow:
            let forward = press.key == .rightArrow
            if press.modifiers.contains(.option) {
                let target = forward ? keyframe(after: preview.position, in: studio.keyframes)
                                     : keyframe(before: preview.position, in: studio.keyframes)
                if let target { preview.pause(); preview.seek(to: target) }
            } else {
                preview.step((forward ? 1 : -1) * (press.modifiers.contains(.shift) ? second : 1))
            }
        default:
            switch press.characters.lowercased() {
            case "i": studio.setStart(preview.position); preview.seek(to: studio.current?.start ?? preview.position)
            case "o": studio.setEnd(preview.position + 1)
            default: return .ignored
            }
        }
        return .handled
    }

    private func chooseFile() {
        let panel = NSOpenPanel()
        panel.message = L("studio.choosePrompt")
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.movie, .audio, .audiovisualContent, .text, .data]
        if panel.runModal() == .OK, let url = panel.url { studio.open(path: url.path) }
    }
}

// ---- the picture --------------------------------------------------------------------------

/// macOS's player view without its own controls (the transport bar below is the control).
struct PlayerSurface: NSViewRepresentable {
    let player: AVPlayer

    func makeNSView(context: Context) -> AVPlayerView {
        let view = AVPlayerView()
        view.controlsStyle = .none
        view.videoGravity = .resizeAspect
        view.player = player
        return view
    }

    func updateNSView(_ view: AVPlayerView, context: Context) {
        if view.player !== player { view.player = player }
    }
}

struct PreviewSurface: View {
    let preview: PreviewPlayer
    let source: StudioSource

    var body: some View {
        ZStack {
            Color.black
            switch preview.phase {
            case .ready:
                if source.hasVideo {
                    PlayerSurface(player: preview.player)
                } else {
                    Image(systemName: "waveform").font(.system(size: 64)).foregroundStyle(.white.opacity(0.4))
                    // The player still plays the sound.
                    PlayerSurface(player: preview.player).frame(width: 1, height: 1).opacity(0)
                }
            case .preparing(let progress):
                VStack(spacing: 10) {
                    ProgressView(value: progress).progressViewStyle(.linear).frame(width: 240)
                    Text(L("studioNative.preparing", Int((progress * 100).rounded())))
                        .foregroundStyle(.white.opacity(0.8))
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("studio.preparing")
            case .failed:
                Label(L("studioNative.previewFailed"), systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.white.opacity(0.8))
                    .padding()
            case .none:
                Label(L("studioNative.noPreview"), systemImage: "doc.text")
                    .foregroundStyle(.white.opacity(0.7))
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("studio.preview")
    }
}

/// ⏮ ◀︎ ▶︎ ▶︎ ⏭, the playhead's time and frame, and the frame rate.
struct Transport: View {
    let studio: Studio
    let preview: PreviewPlayer

    var body: some View {
        let grid = studio.grid
        HStack(spacing: 14) {
            Group {
                button(L("studioNative.toStart"), "backward.end.fill") {
                    preview.pause()
                    preview.seek(to: studio.current?.start ?? 0)
                }
                button(L("studioNative.prevFrame"), "backward.frame.fill") { preview.step(-1) }
                button(preview.isPlaying ? L("studioNative.pause") : L("studioNative.play"),
                       preview.isPlaying ? "pause.fill" : "play.fill") { preview.togglePlay(from: studio.current?.start) }
                    .font(.title2)
                button(L("studioNative.nextFrame"), "forward.frame.fill") { preview.step(1) }
                button(L("studioNative.toEnd"), "forward.end.fill") {
                    preview.pause()
                    preview.seek(to: max(0, (studio.current?.end ?? grid.count) - 1))
                }
            }
            .disabled(preview.phase != .ready)
            Spacer()
            Text(grid.label(preview.position))
                .font(.system(.title3, design: .monospaced).weight(.medium))
                .accessibilityIdentifier("studio.playhead")
            if grid.isFrames {
                Text(L("studioNative.frame", preview.position))
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .accessibilityIdentifier("studio.playheadFrame")
            }
            if let rate = grid.rate {
                Badge(text: L("studioNative.fps", Format.fps(rate)))
                    .help(studio.source?.variableFrameRate == true ? L("studioNative.variableRate") : "")
            }
        }
    }

    private func button(_ title: String, _ symbol: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { Image(systemName: symbol) }
            .buttonStyle(.borderless)
            .help(title)
            .accessibilityLabel(title)
    }
}

// ---- the timeline -------------------------------------------------------------------------

/// The filmstrip with the active piece between two yellow handles (as the Photos app trims a
/// clip), the other pieces outlined, keyframe ticks in lossless mode, and the playhead.
struct TrimTimeline: View {
    @Bindable var studio: Studio
    let preview: PreviewPlayer
    @State private var dragging: Handle?
    /// Where the dragged handle was when it was grabbed: a click without a move moves nothing.
    @State private var grabbed: Int?

    enum Handle { case start, end, playhead }

    private let handleWidth: CGFloat = 14
    private let stripHeight: CGFloat = 64

    var body: some View {
        GeometryReader { geometry in
            let width = max(1, geometry.size.width - handleWidth * 2)
            let grid = studio.grid
            let x = { (position: Int) -> CGFloat in handleWidth + CGFloat(position) / CGFloat(grid.count) * width }
            let position = { (x: CGFloat) -> Int in grid.clamp(Int(((x - handleWidth) / width * CGFloat(grid.count)).rounded())) }

            ZStack(alignment: .topLeading) {
                // The filmstrip.
                HStack(spacing: 0) {
                    if preview.filmstrip.isEmpty {
                        Rectangle().fill(.quaternary)
                    } else {
                        ForEach(Array(preview.filmstrip.enumerated()), id: \.offset) { _, image in
                            Image(decorative: image, scale: 2)
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                                .frame(width: width / CGFloat(preview.filmstrip.count), height: stripHeight)
                                .clipped()
                        }
                    }
                }
                .frame(width: width, height: stripHeight)
                .clipShape(.rect(cornerRadius: 4))
                .offset(x: handleWidth)
                .onAppear { preview.makeFilmstrip(count: Int(width / (stripHeight * 16 / 9)) + 1, height: stripHeight) }
                .onChange(of: preview.phase) { preview.makeFilmstrip(count: Int(width / (stripHeight * 16 / 9)) + 1, height: stripHeight) }
                .onChange(of: geometry.size.width) { preview.makeFilmstrip(count: Int(width / (stripHeight * 16 / 9)) + 1, height: stripHeight) }

                // Outside the active piece: dimmed. The other pieces: outlined.
                if let active = studio.current {
                    Rectangle().fill(.black.opacity(0.55))
                        .frame(width: max(0, x(active.start) - handleWidth), height: stripHeight)
                        .offset(x: handleWidth)
                    Rectangle().fill(.black.opacity(0.55))
                        .frame(width: max(0, handleWidth + width - x(active.end)), height: stripHeight)
                        .offset(x: x(active.end))
                    ForEach(Array(studio.segments.enumerated()), id: \.element.id) { index, piece in
                        if index != studio.active {
                            RoundedRectangle(cornerRadius: 3)
                                .strokeBorder(Color.accentColor, lineWidth: 2)
                                .background(Color.accentColor.opacity(0.18))
                                .frame(width: max(2, x(piece.end) - x(piece.start)), height: stripHeight)
                                .offset(x: x(piece.start))
                                .onTapGesture { studio.active = index }
                        }
                    }
                    selection(active, x: x, position: position)
                }

                // Keyframes (where a lossless cut can start): one drawing, not a view each (an
                // all-intra source has a keyframe on every frame).
                if studio.trimMode == .lossless {
                    Canvas { context, _ in
                        var ticks = Path()
                        var last = -CGFloat.infinity
                        for key in studio.keyframes {
                            let at = x(key)
                            guard at - last >= 1 else { continue }  // one per point is all an eye sees
                            ticks.addRect(CGRect(x: at, y: stripHeight - 8, width: 1, height: 8))
                            last = at
                        }
                        context.fill(ticks, with: .color(.white.opacity(0.9)))
                    }
                    .frame(height: stripHeight)
                    .allowsHitTesting(false)
                }

                // The playhead: its own view, so 60 updates a second redraw only it.
                Playhead(preview: preview, x: x, height: stripHeight)

                // The time ruler.
                Ruler(grid: grid, width: width)
                    .offset(x: handleWidth, y: stripHeight + 8)
            }
            .coordinateSpace(.named("timeline"))
            .contentShape(.rect)
            // Click or drag on the strip: move the playhead there (frame-exact).
            .gesture(DragGesture(minimumDistance: 0).onChanged { value in
                guard dragging == nil || dragging == .playhead else { return }
                dragging = .playhead
                preview.pause()
                preview.seek(to: min(position(value.location.x), grid.count - 1))
            }.onEnded { _ in dragging = nil })
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("studio.timeline")
    }

    @ViewBuilder
    private func selection(_ active: TrimSegment, x: @escaping (Int) -> CGFloat, position: @escaping (CGFloat) -> Int) -> some View {
        let left = x(active.start)
        let right = x(active.end)
        // The yellow frame around the piece.
        RoundedRectangle(cornerRadius: 4)
            .strokeBorder(Color.yellow, lineWidth: 3)
            .frame(width: max(handleWidth * 2, right - left + handleWidth * 2), height: stripHeight)
            .offset(x: left - handleWidth)
            .allowsHitTesting(false)
        handle(.start, systemImage: "chevron.compact.left")
            .offset(x: left - handleWidth)
            .gesture(DragGesture(minimumDistance: 0, coordinateSpace: .named("timeline")).onChanged { value in
                if dragging != .start { grabbed = active.start }
                dragging = .start
                preview.pause()
                let from = x(grabbed ?? active.start)
                studio.setStart(position(from + value.translation.width))
                preview.seek(to: studio.current?.start ?? 0)
            }.onEnded { _ in dragging = nil; grabbed = nil })
            .accessibilityElement()
            .accessibilityLabel(L("studioNative.startHandle"))
            .accessibilityValue(studio.grid.label(active.start))
            .accessibilityAdjustableAction { direction in
                studio.nudgeStart(direction == .increment ? 1 : -1)
            }
            .accessibilityIdentifier("studio.startHandle")
        handle(.end, systemImage: "chevron.compact.right")
            .offset(x: right)
            .gesture(DragGesture(minimumDistance: 0, coordinateSpace: .named("timeline")).onChanged { value in
                if dragging != .end { grabbed = active.end }
                dragging = .end
                preview.pause()
                let from = x(grabbed ?? active.end)
                studio.setEnd(position(from + value.translation.width))
                preview.seek(to: max(0, (studio.current?.end ?? 1) - 1))
            }.onEnded { _ in dragging = nil; grabbed = nil })
            .accessibilityElement()
            .accessibilityLabel(L("studioNative.endHandle"))
            .accessibilityValue(studio.grid.label(active.end))
            .accessibilityAdjustableAction { direction in
                studio.nudgeEnd(direction == .increment ? 1 : -1)
            }
            .accessibilityIdentifier("studio.endHandle")
    }

    private func handle(_ which: Handle, systemImage: String) -> some View {
        UnevenRoundedRectangle(topLeadingRadius: which == .start ? 5 : 0, bottomLeadingRadius: which == .start ? 5 : 0,
                               bottomTrailingRadius: which == .end ? 5 : 0, topTrailingRadius: which == .end ? 5 : 0)
            .fill(Color.yellow)
            .frame(width: handleWidth, height: stripHeight)
            .overlay(Image(systemName: systemImage).font(.body.weight(.heavy)).foregroundStyle(.black.opacity(0.7)))
            .contentShape(.rect)
            .pointerStyle(.frameResize(position: which == .start ? .leading : .trailing))
    }
}

struct Playhead: View {
    let preview: PreviewPlayer
    let x: (Int) -> CGFloat
    let height: CGFloat

    var body: some View {
        Rectangle().fill(.white)
            .frame(width: 2, height: height + 10)
            .shadow(radius: 1)
            .offset(x: x(preview.position) - 1, y: -5)
            .allowsHitTesting(false)
    }
}

/// Times under the filmstrip, at a round step that fits.
struct Ruler: View {
    let grid: TimeGrid
    let width: CGFloat

    /// "1:05", or "1:05.5" when the step is below a second (never rounded up into the next).
    static func label(_ seconds: Double, tenths: Bool) -> String {
        if tenths {
            let t = Int((seconds * 10).rounded())
            return String(format: "%d:%02d.%d", t / 600, t % 600 / 10, t % 10)
        }
        let s = Int(seconds.rounded())
        return s >= 3600 ? String(format: "%d:%02d:%02d", s / 3600, s % 3600 / 60, s % 60) : String(format: "%d:%02d", s / 60, s % 60)
    }

    var body: some View {
        let duration = grid.seconds(grid.count)
        let steps: [Double] = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600]
        let step = steps.first { duration / $0 <= Double(width / 70) } ?? 3600
        // Only marks whose label fits before the right edge.
        let marks = Array(stride(from: 0.0, through: duration, by: step)).filter { CGFloat($0 / duration) * width <= width - 34 }
        ZStack(alignment: .topLeading) {
            ForEach(marks, id: \.self) { mark in
                VStack(alignment: .leading, spacing: 1) {
                    Rectangle().fill(.tertiary).frame(width: 1, height: 4)
                    Text(Self.label(mark, tenths: step < 1))
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .fixedSize()
                }
                .offset(x: CGFloat(mark / duration) * width)
            }
        }
        .frame(width: width, height: 18, alignment: .topLeading)
        .accessibilityHidden(true)
    }
}

// ---- the numbers --------------------------------------------------------------------------

/// The active piece in numbers: start and end (time and frame), each a frame earlier or later,
/// "from the playhead" (I/O), and the length.
struct RangeEditor: View {
    @Bindable var studio: Studio
    let preview: PreviewPlayer

    var body: some View {
        if let piece = studio.current {
            let grid = studio.grid
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 18) {
                    edge(L("studio.trim.start"), piece.start, key: "I", identifier: "studio.start",
                         set: { studio.setStart($0); preview.seek(to: studio.current?.start ?? 0) },
                         nudge: { studio.nudgeStart($0); preview.seek(to: studio.current?.start ?? 0) },
                         here: { studio.setStart(preview.position); preview.seek(to: studio.current?.start ?? 0) },
                         current: { studio.current?.start ?? 0 })
                    edge(L("studio.trim.end"), piece.end, key: "O", identifier: "studio.end",
                         set: { studio.setEnd($0) },
                         nudge: { studio.nudgeEnd($0); preview.seek(to: max(0, (studio.current?.end ?? 1) - 1)) },
                         here: { studio.setEnd(preview.position + 1) },
                         current: { studio.current?.end ?? 0 })
                    VStack(alignment: .leading, spacing: 2) {
                        Text(L("studioNative.duration")).font(.caption).foregroundStyle(.secondary)
                        Text(grid.isFrames
                             ? L("studioNative.durationFrames", TimeGrid.clock(grid.seconds(piece.length)), piece.length)
                             : TimeGrid.clock(grid.seconds(piece.length)))
                            .font(.system(.body, design: .monospaced).weight(.semibold))
                            .accessibilityIdentifier("studio.length")
                    }
                }
                Group {
                    if studio.trimMode == .lossless {
                        Label(studio.keyframesLoaded ? L("studioNative.snapsToKeyframes", studio.keyframes.count)
                                                     : L("studioNative.keyframesLoading"),
                              systemImage: "key")
                    } else {
                        Label(L("studioNative.accurateExact"), systemImage: "checkmark.seal")
                    }
                    if studio.source?.variableFrameRate == true {
                        Label(L("studioNative.variableRate"), systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                    }
                    Text(L("studioNative.keyHints")).foregroundStyle(.tertiary)
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
    }

    private func edge(_ title: String, _ position: Int, key: String, identifier: String, set: @escaping (Int) -> Void,
                      nudge: @escaping (Int) -> Void, here: @escaping () -> Void,
                      current: @escaping () -> Int) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            HStack(spacing: 4) {
                Button { nudge(-1) } label: { Image(systemName: "chevron.left") }
                    .help(L("studioNative.prevFrame")).accessibilityLabel("\(title) \(L("studioNative.prevFrame"))")
                TimeField(grid: studio.grid, position: position, commit: set, current: current)
                    .accessibilityIdentifier(identifier)
                Button { nudge(1) } label: { Image(systemName: "chevron.right") }
                    .help(L("studioNative.nextFrame")).accessibilityLabel("\(title) \(L("studioNative.nextFrame"))")
                Button(action: here) { Text(key).font(.system(.callout, design: .monospaced).weight(.bold)) }
                    .help(title == L("studio.trim.start") ? L("studioNative.setStart") : L("studioNative.setEnd"))
                    .accessibilityLabel(title == L("studio.trim.start") ? L("studioNative.setStart") : L("studioNative.setEnd"))
            }
            .controlSize(.small)
            if studio.grid.isFrames {
                Text(L("studioNative.frame", position)).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
            }
        }
    }
}

/// A time ("1:02.345") that snaps to the grid when entered.
struct TimeField: View {
    let grid: TimeGrid
    let position: Int
    let commit: (Int) -> Void
    /// The model's value right after a commit (the piece may have been clamped or snapped).
    let current: () -> Int
    @State private var text = ""
    @FocusState private var editing: Bool

    var body: some View {
        TextField("", text: $text)
            .font(.system(.body, design: .monospaced))
            .frame(width: 104)
            .textFieldStyle(.roundedBorder)
            .multilineTextAlignment(.trailing)
            .focused($editing)
            .onAppear { text = grid.label(position) }
            .onChange(of: position) { _, now in if !editing { text = grid.label(now) } }
            // Return or leaving the field applies it; the field then shows what the piece really
            // got (clamped, or snapped to a keyframe), never the stale value or the typed one.
            .onSubmit { apply() }
            .onChange(of: editing) { _, now in if !now { apply() } }
    }

    private func apply() {
        // The field shows times from the first frame, as the labels do: no origin to add.
        if let seconds = TimeGrid.parse(text) { commit(grid.position(seconds)) }
        text = grid.label(current())
    }
}

/// Every piece (the active one is on the timeline), adding one, chapters, and joining.
struct Pieces: View {
    @Bindable var studio: Studio
    let preview: PreviewPlayer
    let chapters: [StudioChapter]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(L("studio.trim.segments")).font(.subheadline.weight(.semibold))
                Spacer()
                if !chapters.isEmpty {
                    Menu(L("studio.trim.chapters")) {
                        ForEach(Array(chapters.enumerated()), id: \.offset) { _, chapter in
                            Button(chapter.title ?? TimeGrid.clock(chapter.start)) { studio.useChapter(chapter) }
                        }
                    }
                    .fixedSize()
                }
                Button(L("studio.trim.addSegment"), systemImage: "plus") { studio.addSegment() }
                    .accessibilityIdentifier("studio.addSegment")
            }
            ForEach(Array(studio.segments.enumerated()), id: \.element.id) { index, piece in
                HStack(spacing: 10) {
                    Image(systemName: index == studio.active ? "largecircle.fill.circle" : "circle")
                        .foregroundStyle(index == studio.active ? Color.yellow : .secondary)
                    Text(L("studioNative.piece", index + 1)).font(.callout.weight(.medium))
                    Text("\(studio.grid.label(piece.start)) → \(studio.grid.label(piece.end))")
                        .font(.system(.callout, design: .monospaced))
                    Text(studio.grid.isFrames ? L("studioNative.frames", piece.length) : TimeGrid.clock(studio.grid.seconds(piece.length)))
                        .font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    if studio.segments.count > 1 {
                        Button(L("studio.trim.removeSegment")) { studio.removeSegment(at: index) }.buttonStyle(.link)
                    }
                }
                .contentShape(.rect)
                .onTapGesture {
                    studio.active = index
                    preview.seek(to: piece.start)
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("studio.piece")
            }
            if studio.segments.count > 1 {
                Toggle(L("studio.trim.join"), isOn: $studio.join).toggleStyle(.checkbox)
            }
        }
    }
}
