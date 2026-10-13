import SwiftUI

/// Sistem: the tools the app relies on (yt-dlp, a JavaScript runtime, FFmpeg) and Berk's
/// Safari session, from `/api/doctor`, with the one step that fixes each problem.
struct DoctorView: View {
    let client: APIClient

    private enum Phase {
        case loading
        case failed(APIError)
        case ready(DoctorReport)
    }

    @State private var phase: Phase = .loading

    var body: some View {
        content
            .toolbar {
                ToolbarItem {
                    Button(L("doctor.refresh"), systemImage: "arrow.clockwise") { Task { await load() } }
                        .help(L("doctor.refresh"))
                        .disabled(isLoading)  // one report at a time; overlapping loads would race
                        .accessibilityIdentifier("doctor.refresh")
                }
            }
            .task { await load() }
    }

    @ViewBuilder private var content: some View {
        switch phase {
        case .loading:
            ProgressView(L("doctor.loading"))
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        case .failed(let error):
            ErrorStateView(error: error) { Task { await load() } }
        case .ready(let report):
            Form {
                Section {
                    Label {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(L("doctor.status.\(report.status.rawValue)")).font(.headline)
                            Text(L("doctor.subtitle")).foregroundStyle(.secondary)
                        }
                    } icon: {
                        StatusIcon(status: report.status).font(.title)
                    }
                    .accessibilityIdentifier("doctor.summary")
                }
                ForEach(report.checks) { check in
                    CheckSection(check: check, client: client) { Task { await load(quiet: true) } }
                }
            }
            .formStyle(.grouped)
        }
    }

    private var isLoading: Bool {
        if case .loading = phase { return true }
        return false
    }

    /// A refresh after an update keeps the report on screen (and the update's message with it).
    private func load(quiet: Bool = false) async {
        if !quiet { phase = .loading }
        do {
            phase = .ready(try await client.doctor())
        } catch {
            phase = .failed(APIError.from(error))
        }
    }
}

struct StatusIcon: View {
    let status: CheckStatus

    var body: some View {
        switch status {
        case .ok: Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
        case .warn: Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.yellow)
        case .error: Image(systemName: "xmark.octagon.fill").foregroundStyle(.red)
        }
    }
}

struct CheckSection: View {
    let check: DoctorCheck
    let client: APIClient
    let reload: () -> Void

    /// The values worth a row, in reading order; anything newer the backend adds comes last.
    nonisolated static let order: [String: [String]] = [
        "yt_dlp": ["version", "channel", "origin", "ejs_version"],
        "js_runtime": ["active"],
        "ffmpeg": ["version", "ffmpeg_path", "ffprobe_path"],
        "aria2c": ["version", "path"],
    ]
    nonisolated static let structured: Set<String> = ["capabilities", "found", "missing_optional", "state"]

    var body: some View {
        Section {
            ForEach(rows, id: \.key) { row in
                LabeledContent(localizedIfPresent("doctor.label.\(row.key)") ?? row.key) {
                    Text(row.value)
                        .font(.system(.callout, design: .monospaced))
                        .textSelection(.enabled)
                        .multilineTextAlignment(.trailing)
                }
            }
            ForEach(runtimes, id: \.name) { runtime in
                LabeledContent(runtime.name) {
                    Text(runtime.version)
                        .font(.system(.callout, design: .monospaced))
                        .textSelection(.enabled)
                        .help(runtime.path)
                }
            }
            if let capabilities = check.values["capabilities"], case .object(let map) = capabilities, !map.isEmpty {
                Capabilities(map: map)
            }
            ForEach(missing, id: \.self) { key in
                Label(localizedIfPresent("doctor.missing.\(key)") ?? key, systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if check.id == "yt_dlp" { UpdateYtdlp(client: client, done: reload) }
            if check.id == "safari_session" { SafariSession(state: check.values["state"]?.string ?? "", fix: check.fix.kind, client: client) }
            if check.status != .ok, check.fix.kind == "command" {
                VStack(alignment: .leading, spacing: 6) {
                    Text(L("doctor.fixHint")).foregroundStyle(.secondary)
                    HStack {
                        Text(check.fix.command)
                            .font(.system(.callout, design: .monospaced))
                            .textSelection(.enabled)
                        Spacer()
                        CopyButton(value: check.fix.command)
                    }
                }
            }
        } header: {
            HStack(spacing: 8) {
                StatusIcon(status: check.status)
                Text(localizedIfPresent("doctor.check.\(check.id)") ?? check.id)
                    .accessibilityIdentifier("doctor.check.\(check.id)")
                Badge(text: L("doctor.checkStatus.\(check.status.rawValue)"),
                      tone: check.status == .ok ? .ok : check.status == .warn ? .warn : .danger)
            }
        } footer: {
            if let help = localizedIfPresent("doctor.checkHelp.\(check.id)") {
                Text(help).font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var rows: [(key: String, value: String)] {
        let wanted = Self.order[check.id] ?? []
        let rest = check.values.keys.filter { !wanted.contains($0) && !Self.structured.contains($0) }.sorted()
        return (wanted + rest).compactMap { key in
            guard let value = check.values[key] else { return nil }
            return (key, value.display.isEmpty ? "–" : value.display)
        }
    }

    private var runtimes: [(name: String, version: String, path: String)] {
        guard case .array(let found)? = check.values["found"] else { return [] }
        return found.compactMap { item in
            guard case .object(let runtime) = item, let name = runtime["name"]?.string else { return nil }
            return (name, runtime["version"]?.string ?? "–", runtime["path"]?.string ?? "")
        }
    }

    private var missing: [String] {
        guard case .array(let keys)? = check.values["missing_optional"] else { return [] }
        return keys.compactMap(\.string)
    }
}

/// What this FFmpeg build can do, in a fixed order; a capability the app does not know yet
/// still shows, by its key.
struct Capabilities: View {
    nonisolated static let order = ["libx264", "libx265", "libsvtav1", "videotoolbox_h264", "videotoolbox_hevc", "aac", "libopus",
                        "libmp3lame", "flac", "webp", "gif", "loudnorm", "palettegen", "subtitles_filter"]
    let map: [String: JSONValue]

    var body: some View {
        let keys = Self.order.filter { map[$0] != nil } + map.keys.filter { !Self.order.contains($0) }.sorted()
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), alignment: .leading)], alignment: .leading, spacing: 6) {
            ForEach(keys, id: \.self) { key in
                let available = map[key] == .bool(true)
                Label {
                    Text(localizedIfPresent("doctor.capability.\(key)") ?? key)
                        .foregroundStyle(available ? .primary : .tertiary)
                } icon: {
                    Image(systemName: available ? "checkmark.circle.fill" : "xmark.circle")
                        .foregroundStyle(available ? .green : .secondary)
                }
                .font(.callout)
            }
        }
        .padding(.vertical, 2)
    }
}

/// "yt-dlp'yi güncelle": upgrades the lock file, so the update sticks (CLAUDE.md gotcha 2).
struct UpdateYtdlp: View {
    let client: APIClient
    let done: () -> Void

    private enum Phase {
        case idle, running
        case finished(String)
        case failed(APIError)
    }

    @State private var phase: Phase = .idle

    var body: some View {
        LabeledContent {
            Button {
                Task { await run() }
            } label: {
                if case .running = phase {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.small)
                        Text(L("doctor.updating"))
                    }
                } else {
                    Label(L("doctor.updateYtdlp"), systemImage: "arrow.down.circle")
                }
            }
            .disabled(isRunning)
            .accessibilityIdentifier("doctor.updateYtdlp")
        } label: {
            Text(L("doctor.updateHelp")).font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        switch phase {
        case .finished(let text):
            Label(text, systemImage: "checkmark.circle").foregroundStyle(.green)
        case .failed(let error):
            VStack(alignment: .leading, spacing: 2) {
                Label(ErrorCopy.title(error.code), systemImage: "xmark.octagon.fill").foregroundStyle(.red)
                Text(ErrorCopy.body(error.code)).font(.callout).foregroundStyle(.secondary)
                if !error.raw.isEmpty { RawDetails(raw: error.raw) }
            }
            .accessibilityIdentifier("doctor.updateFailed")
        default:
            EmptyView()
        }
    }

    private var isRunning: Bool {
        if case .running = phase { return true }
        return false
    }

    private func run() async {
        phase = .running
        do {
            let result = try await client.updateYtdlp()
            phase = .finished(result.changed ? L("doctor.updated", result.before.version, result.after.version)
                                             : L("doctor.upToDate", result.after.version))
            done()
        } catch {
            phase = .failed(APIError.from(error))
        }
    }
}

/// What the Safari session means for age-restricted videos, and the one step that fixes it.
struct SafariSession: View {
    let state: String
    let fix: String
    let client: APIClient
    @State private var failure: String?

    var body: some View {
        if let text = localizedIfPresent("doctor.session.\(state)") {
            Label(text, systemImage: warns ? "exclamationmark.triangle.fill" : "info.circle")
                .foregroundStyle(warns ? AnyShapeStyle(.orange) : AnyShapeStyle(.secondary))
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("doctor.session")
        }
        if fix == "full_disk_access" {
            Button(L("doctor.openFullDiskAccess"), systemImage: "gearshape") {
                failure = nil
                Task {
                    do { try await client.openFullDiskAccess() } catch { failure = APIError.from(error).code }
                }
            }
        }
        if state == "off" {
            SettingsLink { Label(L("doctor.openSettings"), systemImage: "gearshape") }
        }
        if let failure {
            // The body is the remedy ("go there by hand"): never just the title.
            VStack(alignment: .leading, spacing: 2) {
                Label(ErrorCopy.title(failure), systemImage: "xmark.octagon.fill").foregroundStyle(.red)
                Text(ErrorCopy.body(failure)).font(.callout).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var warns: Bool { !["signed_in", "off", "unknown"].contains(state) }
}
