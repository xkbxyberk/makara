import AppKit
import SwiftUI

/// The menu bar item's panel (P4): what is downloading, the copied link, pause or resume
/// everything, the window, and Quit. It lives as long as the app, window or not.
public struct MenuBarView: View {
    let model: AppModel
    @Environment(\.openWindow) private var openWindow

    public init(model: AppModel) { self.model = model }

    private var active: [Job] {
        model.jobList.filter { $0.status.isActive || $0.status == .paused }
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(L("app.name")).font(.headline)
                Spacer()
                Text(statusText).font(.caption).foregroundStyle(.secondary)
            }
            if active.isEmpty {
                Text(L("menubar.idle"))
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 6)
            } else {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(active.prefix(5)) { job in row(job) }
                    if active.count > 5 {
                        Text(L("menubar.more", active.count - 5)).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            Divider()
            VStack(alignment: .leading, spacing: 2) {
                item(L("menu.inspectClipboard"), "doc.on.clipboard") {
                    model.inspectClipboard()
                    show()
                }
                .disabled(!model.isReady)
                if active.contains(where: { $0.status.isActive && $0.kind == "download" }) {
                    item(L("queue.pauseAll"), "pause.circle") { Task { try? await model.backend.client.pauseAll() } }
                }
                if active.contains(where: { $0.status == .paused }) {
                    item(L("queue.resumeAll"), "play.circle") { Task { try? await model.backend.client.resumeAll() } }
                }
                item(L("menubar.downloads"), "arrow.down.circle") {
                    model.route = .download
                    show()
                }
                item(L("menubar.open"), "macwindow") { show() }
            }
            Divider()
            item(L("menubar.quit"), "power") { NSApp.terminate(nil) }
        }
        .padding(12)
        .frame(width: 320)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("menubar")
    }

    private var statusText: String {
        switch model.backend.state {
        case .ready: model.activeCount > 0 ? L("menubar.activeCount", model.activeCount) : L("menubar.ready")
        case .failed: L("menubar.failed")
        default: L("backend.starting")
        }
    }

    private func row(_ job: Job) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(job.title ?? job.sourceUrl ?? "")
                .font(.callout)
                .lineLimit(1)
                .truncationMode(.middle)
            if job.isIndeterminate && job.status == .running {
                ProgressView().progressViewStyle(.linear)
            } else {
                ProgressView(value: min(max(job.progress ?? 0, 0), 1)).progressViewStyle(.linear)
            }
            HStack(spacing: 8) {
                Text(localizedIfPresent("queue.stage.\(job.stage ?? job.status.rawValue)")
                     ?? localizedIfPresent("queue.status.\(job.status.rawValue)") ?? job.status.rawValue)
                if job.status == .running, let progress = job.progress, progress > 0 {
                    Text("\(Int((progress * 100).rounded()))%")
                }
                if job.status == .running, let speed = job.speed, speed > 0 { Text(L("queue.speed", Format.bytes(speed))) }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            .monospacedDigit()
        }
    }

    private func item(_ title: String, _ symbol: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: symbol).frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
        }
        .buttonStyle(MenuRowStyle())
    }

    /// The main window, in front (the app may have no Dock icon, so it must activate itself).
    private func show() {
        openWindow(id: "main")
        NSApp.activate()
    }
}

/// A row that highlights under the pointer, as menu items do.
private struct MenuRowStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View { MenuRow(label: configuration.label) }
}

private struct MenuRow<Content: View>: View {
    let label: Content
    @State private var hovering = false
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        label
            .padding(.horizontal, 6)
            .padding(.vertical, 4)
            .foregroundStyle(hovering && isEnabled ? Color.white : Color.primary)
            .background(RoundedRectangle(cornerRadius: 5).fill(hovering && isEnabled ? Color.accentColor : .clear))
            .opacity(isEnabled ? 1 : 0.45)
            .onHover { hovering = $0 }
    }
}
