import SwiftUI

/// İndirmeler: the live job list from the app's event stream (the same one that drives the
/// sidebar and Dock badges), with cancel, retry, remove and "show in Finder".
struct QueueView: View {
    let jobs: [Job]
    let loaded: Bool
    let connection: AppModel.Connection
    let client: APIClient

    var body: some View {
        Group {
            if !loaded {
                ProgressView(L("queue.loading"))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if jobs.isEmpty {
                ContentUnavailableView {
                    Label(L("queue.emptyTitle"), systemImage: "arrow.down.circle")
                } description: {
                    Text(L("queue.emptyBody"))
                }
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("queue.empty")
            } else {
                List(jobs) { job in
                    JobRow(job: job, client: client)
                        .listRowSeparator(.visible)
                }
                .listStyle(.inset)
                .alternatingRowBackgrounds(.disabled)
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("queue.list")
            }
        }
        .toolbar {
            // Both always there (a toolbar item that comes and goes resizes the bar: gotcha 39).
            ToolbarItemGroup {
                Button { Task { try? await client.pauseAll() } } label: {
                    Label(L("queue.pauseAll"), systemImage: "pause.circle")
                }
                .help(L("queue.pauseAll"))
                .disabled(!jobs.contains { $0.status.isActive && $0.kind == "download" })
                .accessibilityIdentifier("queue.pauseAll")
                Button { Task { try? await client.resumeAll() } } label: {
                    Label(L("queue.resumeAll"), systemImage: "play.circle")
                }
                .help(L("queue.resumeAll"))
                .disabled(!jobs.contains { $0.status == .paused })
                .accessibilityIdentifier("queue.resumeAll")
            }
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            if connection == .reconnecting {
                Label(L("queue.reconnecting"), systemImage: "wifi.exclamationmark")
                    .font(.callout)
                    .foregroundStyle(.orange)
                    .frame(maxWidth: .infinity)
                    .padding(8)
                    .background(.bar)
                    .accessibilityIdentifier("queue.reconnecting")
            }
        }
    }
}

struct JobRow: View {
    let job: Job
    let client: APIClient
    @State private var failure: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.title3)
                    .foregroundStyle(iconColor)
                    .frame(width: 22)
                Text(job.title ?? job.sourceUrl ?? "")
                    .font(.body.weight(.medium))
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .help(job.sourceUrl ?? "")
                Spacer(minLength: 8)
                if let mode = job.mode { Badge(text: localizedIfPresent("mode.\(mode)") ?? mode) }
                if job.usedSession == true {
                    Badge(text: L("queue.usedSession"), tone: .warn).help(L("queue.usedSessionHelp"))
                }
                Badge(text: localizedIfPresent("queue.status.\(job.status.rawValue)") ?? job.status.rawValue, tone: tone)
                    .accessibilityIdentifier("job.status")
                actions
            }
            if job.status == .running || job.status == .queued || job.status == .paused {
                progress
            }
            if job.status == .failed {
                failed
            }
            if job.status == .done {
                files
                ForEach(job.warnings ?? [], id: \.self) { warning in
                    Label(warningText(warning), systemImage: "exclamationmark.triangle.fill")
                        .font(.callout)
                        .foregroundStyle(.orange)
                }
            }
            if let failure {
                // As the web row: a code this app does not know yet is shown as it is.
                Label(localizedIfPresent("error.\(failure).title") ?? failure, systemImage: "xmark.octagon.fill")
                    .font(.callout)
                    .foregroundStyle(.red)
            }
        }
        .padding(.vertical, 6)
        .contextMenu { menu }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("job")
    }

    // ---- parts ------------------------------------------------------------------------------

    private var icon: String {
        switch job.status {
        case .done: "checkmark.circle.fill"
        case .failed: "xmark.octagon.fill"
        default: job.mode == "studio" ? "scissors" : "arrow.down.circle"
        }
    }

    private var iconColor: Color {
        switch job.status {
        case .done: .green
        case .failed: .red
        default: .secondary
        }
    }

    private var tone: Badge.Tone {
        switch job.status {
        case .done: .ok
        case .failed: .danger
        case .running: .accent
        default: .neutral
        }
    }

    private var stageText: String {
        let stage = job.stage ?? job.status.rawValue
        return localizedIfPresent("queue.stage.\(stage)") ?? stage
    }

    @ViewBuilder private var actions: some View {
        HStack(spacing: 2) {
            if canPause {
                iconButton(L("queue.pause"), "pause.circle") { try await client.pause(job: job.id) }
            }
            if job.status == .paused {
                iconButton(L("queue.resume"), "play.circle") { try await client.resume(job: job.id) }
            }
            if job.status.isActive || job.status == .paused {
                iconButton(L("queue.cancel"), "xmark.circle") { try await client.cancel(job: job.id) }
            }
            if job.status == .failed || job.status == .cancelled {
                iconButton(L("queue.retry"), "arrow.clockwise") { try await client.retry(job: job.id) }
            }
            if job.status != .running {
                iconButton(L("queue.remove"), "minus.circle", help: L("queue.removeHelp")) {
                    try await client.remove(job: job.id)
                }
            }
        }
    }

    /// Downloads only: a Stüdyo run cannot continue where it stopped. Not while files are placed.
    private var canPause: Bool {
        job.status.isActive && job.kind == "download" && !["finalizing", "cancelling", "pausing"].contains(job.stage ?? "")
    }

    @ViewBuilder private var menu: some View {
        if canPause {
            Button(L("queue.pause")) { run { try await client.pause(job: job.id) } }
        }
        if job.status == .paused {
            Button(L("queue.resume")) { run { try await client.resume(job: job.id) } }
        }
        if job.status.isActive || job.status == .paused {
            Button(L("queue.cancel")) { run { try await client.cancel(job: job.id) } }
        }
        if job.status == .failed || job.status == .cancelled {
            Button(L("queue.retry")) { run { try await client.retry(job: job.id) } }
        }
        if job.status == .done, !job.outputFiles.isEmpty {
            Button(L("queue.reveal")) { run { try await client.reveal(job: job.id, file: 0) } }
        }
        if let source = job.sourceUrl {
            Button(L("queue.copyLink")) {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(source, forType: .string)
            }
        }
        if job.status != .running {
            Divider()
            Button(L("queue.remove")) { run { try await client.remove(job: job.id) } }
        }
    }

    private var progress: some View {
        VStack(alignment: .leading, spacing: 3) {
            Group {
                if job.status == .running, job.stage == "downloading", let pieces = job.pieces, !pieces.isEmpty {
                    SegmentBar(pieces: pieces)
                } else if job.isIndeterminate {
                    ProgressView()
                } else {
                    ProgressView(value: min(max(job.progress ?? 0, 0), 1))
                }
            }
            .progressViewStyle(.linear)
            .accessibilityLabel(stageText)
            HStack(spacing: 12) {
                if job.stage == "waiting_retry", let at = job.retryAt {
                    // Why and when, counting down: the failure passes by itself more often than not.
                    TimelineView(.periodic(from: .now, by: 1)) { context in
                        let left = max(0, at - context.date.timeIntervalSince1970)
                        Text(L("queue.retryIn", (job.attempts ?? 1) + 1, Format.duration(left),
                               localizedIfPresent("error.\(job.errorCode ?? "").title") ?? ""))
                    }
                } else {
                    Text(stageText)
                }
                if job.status == .running {
                    if let progress = job.progress, progress > 0 { Text("\(Int((progress * 100).rounded()))%") }
                    if let index = job.itemIndex, let count = job.itemCount, count > 1 {
                        Text(L("queue.item", index, count))
                    }
                    if let speed = job.speed, speed > 0 { Text(L("queue.speed", Format.bytes(speed))) }
                    if job.stage == "downloading", let connections = job.connections, connections > 0 {
                        Label(L("queue.connections", connections), systemImage: "point.3.connected.trianglepath.dotted")
                            .help(L("queue.connectionsHelp"))
                    }
                    if job.stage == "downloading", let fragments = job.fragments, fragments.count == 2 {
                        Text(L("queue.fragments", fragments[0], fragments[1]))
                    }
                    if let eta = job.eta, eta > 0 { Text(L("queue.eta", Format.duration(eta))) }
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            .monospacedDigit()
        }
        .padding(.leading, 30)
    }

    private var failed: some View {
        let code = job.errorCode ?? "UNKNOWN"
        return VStack(alignment: .leading, spacing: 4) {
            Text(ErrorCopy.title(code)).font(.callout.weight(.semibold))
            Text(ErrorCopy.body(code)).font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if let raw = job.errorRaw, !raw.isEmpty { RawDetails(raw: raw) }
        }
        .padding(.leading, 30)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("job.error")
    }

    private var files: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(job.outputFiles.enumerated()), id: \.offset) { index, file in
                HStack(spacing: 6) {
                    Text(file.split(separator: "/").suffix(2).joined(separator: "/"))
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .textSelection(.enabled)
                    iconButton(L("queue.reveal"), "folder") { try await client.reveal(job: job.id, file: index) }
                }
            }
        }
        .padding(.leading, 30)
    }

    private func warningText(_ warning: JobWarning) -> String {
        guard let format = localizedIfPresent("queue.warning.\(warning.code)") else { return warning.code }
        return String(format: format, warning.key ?? "")
    }

    // ---- actions ----------------------------------------------------------------------------

    private func iconButton(_ title: String, _ symbol: String, help: String? = nil,
                            _ action: @escaping @Sendable () async throws -> Void) -> some View {
        Button { run(action) } label: {
            Image(systemName: symbol).imageScale(.large)
        }
        .buttonStyle(.borderless)
        .help(help ?? title)
        .accessibilityLabel(title)
    }

    private func run(_ action: @escaping @Sendable () async throws -> Void) {
        failure = nil
        Task {
            do { try await action() } catch { failure = APIError.from(error).code }
        }
    }
}

/// The file in segments, as download accelerators draw it (P2): each cell is a slice of the
/// file, filled as far as its bytes are on disk. Several connections show as several regions
/// filling at once; the data comes from aria2c's own piece map or yt-dlp's fragment counter.
struct SegmentBar: View {
    let pieces: String

    var body: some View {
        Canvas { context, size in
            let cells = Array(pieces.utf8).map { min(max(Int($0) - 48, 0), 9) }
            guard !cells.isEmpty else { return }
            let gap: CGFloat = cells.count > 40 ? 1 : 2
            let width = (size.width - gap * CGFloat(cells.count - 1)) / CGFloat(cells.count)
            for (index, level) in cells.enumerated() {
                let rect = CGRect(x: CGFloat(index) * (width + gap), y: 0, width: width, height: size.height)
                context.fill(Path(roundedRect: rect, cornerRadius: 1.5), with: .color(.secondary.opacity(0.18)))
                guard level > 0 else { continue }
                let filled = CGRect(x: rect.minX, y: 0, width: rect.width * CGFloat(level) / 9, height: size.height)
                context.fill(Path(roundedRect: filled, cornerRadius: 1.5), with: .color(.accentColor))
            }
        }
        .frame(height: 7)
        .accessibilityHidden(true)
    }
}
