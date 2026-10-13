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

extension Format {
    static let turkish = Locale(identifier: "tr")
    private static let posix = Locale(identifier: "en_US_POSIX")

    /// "1.2 Mbps" / "128 kbps", as the web page's `formatBitrate`.
    public static func bitrate(_ kbps: Double?) -> String {
        guard let kbps, kbps.isFinite, kbps > 0 else { return "–" }
        return kbps >= 1000 ? String(format: "%.1f %@", locale: posix, kbps / 1000, L("unit.mbps"))
                            : "\(Int(kbps.rounded())) \(L("unit.kbps"))"
    }

    public static func sampleRate(_ hz: Double?) -> String {
        guard let hz, hz.isFinite, hz > 0 else { return "–" }
        return String(format: "%.1f %@", locale: posix, hz / 1000, L("unit.khz"))
    }

    /// A size with its trust marker ("≈1.2 GB"), or "–".
    public static func size(_ bytes: Double?, _ kind: SizeKind) -> String {
        guard let bytes else { return "–" }
        return kind.prefix + Format.bytes(bytes)
    }

    public static func count(_ value: Double?) -> String {
        guard let value, value.isFinite, value > 0 else { return "–" }
        return value.formatted(.number.notation(.compactName).locale(turkish))
    }

    /// yt-dlp gives upload_date as YYYYMMDD.
    public static func uploadDate(_ value: String?) -> String {
        guard let value, value.count == 8, value.allSatisfy(\.isNumber),
              let year = Int(value.prefix(4)), let month = Int(value.dropFirst(4).prefix(2)), let day = Int(value.suffix(2)),
              let date = Calendar(identifier: .gregorian).date(from: DateComponents(year: year, month: month, day: day))
        else { return "–" }
        return date.formatted(Date.FormatStyle(date: .abbreviated, time: .omitted).locale(turkish))
    }

    /// "25", "29.97", "59.94": a frame rate as people say it.
    public static func fps(_ rate: FrameRate) -> String {
        let value = rate.perSecond
        if abs(value - value.rounded()) < 0.005 { return String(Int(value.rounded())) }
        return String(format: "%.2f", locale: posix, value)
    }

    /// A number as JavaScript prints it: 30, not 30.0; 29.97 as is.
    public static func plain(_ value: Double) -> String {
        value == value.rounded() && abs(value) < 1e15 ? String(Int(value)) : String(value)
    }

    /// Language codes into Turkish names. YouTube's audio-description tracks arrive as "en-desc",
    /// which is not a real tag, so the suffix is peeled off first (as `languageName`).
    public static func language(_ code: String?) -> String {
        guard let code, !code.isEmpty else { return L("app.unknown") }
        let base = code.hasSuffix("-desc") ? String(code.dropLast(5)) : code
        return turkish.localizedString(forIdentifier: base) ?? base
    }

    /// A plan notice from its template: `{name}` is the param, `{name|Bu}` falls back to "Bu"
    /// when it is missing, `{name^}` upper-cases it (the web page's notice functions).
    public static func notice(_ template: String, _ params: [String: JSONValue]) -> String {
        var result = ""
        var rest = Substring(template)
        while let open = rest.firstIndex(of: "{"), let close = rest[open...].firstIndex(of: "}") {
            result += rest[..<open]
            var spec = String(rest[rest.index(after: open)..<close])
            let upper = spec.hasSuffix("^")
            if upper { spec.removeLast() }
            let parts = spec.split(separator: "|", maxSplits: 1, omittingEmptySubsequences: false)
            let name = String(parts[0])
            var value: String?
            switch params[name] {
            case .string(let text)?: value = text
            case .number(let number)?: value = plain(number)
            case .bool(let flag)?: value = String(flag)
            default: value = nil
            }
            let text = value ?? (parts.count > 1 ? String(parts[1]) : "")
            result += upper ? text.uppercased(with: posix) : text
            rest = rest[rest.index(after: close)...]
        }
        return result + rest
    }
}

/// A plan notice in words; a code this app does not know yet is shown as it is.
func noticeText(_ notice: Plan.Notice) -> String {
    localizedIfPresent("download.notice.\(notice.code)").map { Format.notice($0, notice.params) } ?? notice.code
}

/// A label with its explanation one hover away (the web page's `<Term>`).
struct Term: View {
    let label: String
    let help: String

    init(_ label: String, help: String) {
        self.label = label
        self.help = help
    }

    /// `term.<key>.label/body` from the catalog.
    init(term key: String) {
        self.init(L("term.\(key).label"), help: L("term.\(key).body"))
    }

    var body: some View {
        Text(label)
            .underline(pattern: .dot, color: .secondary.opacity(0.6))
            .help(help)
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
        .accessibilityElement(children: .contain)
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
