import AppKit
import SwiftUI

/// A backend error code in words: the same table as the web page's `tr.errors`
/// (`error.<CODE>.title/body`; a vitest keeps the two catalogs equal).
public enum ErrorCopy {
    public static func title(_ code: String) -> String {
        localizedIfPresent("error.\(code).title") ?? L("error.UNKNOWN.title")
    }

    public static func body(_ code: String) -> String {
        localizedIfPresent("error.\(code).body") ?? L("error.UNKNOWN.body")
    }
}

/// The web page's numbers, the same way (binary units, as yt-dlp reports them).
public enum Format {
    public static func bytes(_ value: Double?) -> String {
        guard let value, value.isFinite else { return "–" }
        let units = [L("unit.bytes"), L("unit.kib"), L("unit.mib"), L("unit.gib"), L("unit.tib")]
        if value < 1024 { return "\(Int(value)) \(units[0])" }
        var scaled = value
        var unit = 0
        while scaled >= 1024, unit < units.count - 1 {
            scaled /= 1024
            unit += 1
        }
        let digits = scaled >= 100 ? 0 : 1
        return String(format: "%.\(digits)f", locale: Locale(identifier: "en_US_POSIX"), scaled) + " " + units[unit]
    }

    public static func duration(_ seconds: Double?) -> String {
        guard let seconds, seconds.isFinite else { return "–" }
        let total = Int(seconds.rounded())
        let (h, m, s) = (total / 3600, total % 3600 / 60, total % 60)
        return h > 0 ? String(format: "%d:%02d:%02d", h, m, s) : String(format: "%d:%02d", m, s)
    }
}

/// A small tinted capsule: a mode, a status, "Safari oturumuyla".
struct Badge: View {
    enum Tone { case neutral, accent, ok, warn, danger }

    let text: String
    var tone: Tone = .neutral

    var body: some View {
        Text(text)
            .font(.caption.weight(.medium))
            .lineLimit(1)
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .foregroundStyle(color)
            .background(color.opacity(0.13), in: .capsule)
            .fixedSize()
    }

    private var color: Color {
        switch tone {
        case .neutral: .secondary
        case .accent: .accentColor
        case .ok: .green
        case .warn: .orange
        case .danger: .red
        }
    }
}

/// An error code as the web page's ErrorState shows it: what happened, what to do, and the
/// raw message behind a disclosure.
struct ErrorStateView: View {
    let error: APIError
    var retry: (() -> Void)? = nil

    var body: some View {
        ContentUnavailableView {
            Label(ErrorCopy.title(error.code), systemImage: "exclamationmark.triangle.fill")
                .symbolRenderingMode(.multicolor)
        } description: {
            Text(ErrorCopy.body(error.code))
        } actions: {
            if let retry {
                Button(L("app.retry"), systemImage: "arrow.clockwise", action: retry)
            }
            if !error.raw.isEmpty {
                RawDetails(raw: error.raw)
            }
        }
        .accessibilityIdentifier("error.\(error.code)")
    }
}

/// "Ayrıntıları göster": the backend's raw message, selectable, for a bug report.
struct RawDetails: View {
    let raw: String
    @State private var open = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button(open ? L("app.hideDetails") : L("app.showDetails")) { open.toggle() }
                .buttonStyle(.link)
            if open {
                Text(raw)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .frame(maxWidth: 560, alignment: .leading)
                    .padding(8)
                    .background(.quaternary.opacity(0.5), in: .rect(cornerRadius: 6))
            }
        }
    }
}

struct CopyButton: View {
    let value: String
    @State private var copied = false

    var body: some View {
        Button {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(value, forType: .string)
            copied = true
            Task {
                try? await Task.sleep(for: .seconds(1.5))
                copied = false
            }
        } label: {
            Label(copied ? L("app.copied") : L("app.copy"), systemImage: copied ? "checkmark" : "doc.on.doc")
        }
    }
}
