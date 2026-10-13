import Foundation
import Observation

/// The Settings window's state. As in every Mac settings window, a change applies at once: a
/// switch or a picker when it changes, a text field when Berk presses Return or leaves it.
///
/// Each change is sent on its own -- what the backend has, plus that one field -- and in order:
/// sending the whole window once let a refused folder make every later switch fail with it,
/// and a newer save cancelling an older one skipped the older one's undo. A refused switch
/// springs back; a refused text stays on screen, says why, and is not applied.
@MainActor
@Observable
public final class Preferences {
    public enum Phase: Equatable {
        case loading
        case failed(APIError)
        case ready
    }

    public typealias Change = @MainActor (inout AppSettings) -> Void

    public private(set) var phase: Phase = .loading
    /// What the backend has.
    public private(set) var saved: AppSettings?
    /// What the window shows (a text field may hold an edit not applied yet).
    public var draft: AppSettings?
    /// The last refused change, as a code.
    public private(set) var failure: APIError?
    public private(set) var templatePreview: Result<String, APIError>?

    @ObservationIgnored private let client: () -> APIClient
    @ObservationIgnored private var queue: Task<Void, Never>?

    public init(client: @escaping () -> APIClient) { self.client = client }

    public func load() async {
        phase = .loading
        do {
            let settings = try await client().settings()
            saved = settings
            draft = settings
            phase = .ready
            await previewTemplate()
        } catch {
            phase = .failed(APIError.from(error))
        }
    }

    /// Apply one change: shown at once, sent after any change before it. `springBack`: on a
    /// refusal the field shows what is really in effect again (switches and pickers).
    public func apply(_ change: @escaping Change, springBack: Bool) {
        if draft != nil { change(&draft!) }
        let previous = queue
        queue = Task {
            await previous?.value
            guard let saved else { return }
            var next = saved
            change(&next)
            guard next != saved else { return }
            do {
                let stored = try await client().save(next)
                self.saved = stored
                failure = nil
                // Show what the backend kept (a folder it resolved), field by field, and only
                // where the window still shows what was sent: an edit typed meanwhile stays.
                if var shown = draft {
                    Self.adopt(stored, sent: next, into: &shown)
                    draft = shown
                }
            } catch {
                failure = APIError.from(error)
                if springBack, var shown = draft {
                    // Undo this change only: every field it touched goes back to what is saved.
                    var undone = saved
                    change(&undone)
                    Self.revert(changed: undone, saved: saved, in: &shown)
                    draft = shown
                }
            }
        }
    }

    /// The draft's text fields, applied (Return, or leaving the field).
    public func commitText() {
        guard let draft else { return }
        let folder = draft.downloadDir
        let template = draft.filenameTemplate
        apply({ $0.downloadDir = folder; $0.filenameTemplate = template }, springBack: false)
    }

    /// Wait for every change sent so far (tests).
    public func settle() async { await queue?.value }

    public var dirty: Bool { draft != nil && draft != saved }

    static func adopt(_ stored: AppSettings, sent: AppSettings, into shown: inout AppSettings) {
        if shown.downloadDir == sent.downloadDir { shown.downloadDir = stored.downloadDir }
        if shown.filenameTemplate == sent.filenameTemplate { shown.filenameTemplate = stored.filenameTemplate }
        if shown.concurrency == sent.concurrency { shown.concurrency = stored.concurrency }
        if shown.defaultMode == sent.defaultMode { shown.defaultMode = stored.defaultMode }
        if shown.clipboardWatch == sent.clipboardWatch { shown.clipboardWatch = stored.clipboardWatch }
        if shown.notifications == sent.notifications { shown.notifications = stored.notifications }
        if shown.safariLogin == sent.safariLogin { shown.safariLogin = stored.safariLogin }
        shown.defaultFilenameTemplate = stored.defaultFilenameTemplate
    }

    static func revert(changed: AppSettings, saved: AppSettings, in shown: inout AppSettings) {
        if changed.downloadDir != saved.downloadDir { shown.downloadDir = saved.downloadDir }
        if changed.filenameTemplate != saved.filenameTemplate { shown.filenameTemplate = saved.filenameTemplate }
        if changed.concurrency != saved.concurrency { shown.concurrency = saved.concurrency }
        if changed.defaultMode != saved.defaultMode { shown.defaultMode = saved.defaultMode }
        if changed.clipboardWatch != saved.clipboardWatch { shown.clipboardWatch = saved.clipboardWatch }
        if changed.notifications != saved.notifications { shown.notifications = saved.notifications }
        if changed.safariLogin != saved.safariLogin { shown.safariLogin = saved.safariLogin }
    }

    /// The file name the draft's template gives for the sample video.
    public func previewTemplate() async {
        guard let template = draft?.filenameTemplate, !template.isEmpty else { return }
        let sample = [
            "title": L("settings.sample.title"), "channel": L("settings.sample.channel"), "id": L("settings.sample.id"),
            "extractor_key": L("settings.sample.extractor_key"), "upload_date": L("settings.sample.upload_date"),
        ]
        do {
            templatePreview = .success(try await client().previewTemplate(template, sample: sample))
        } catch {
            if !Task.isCancelled { templatePreview = .failure(APIError.from(error)) }
        }
    }
}
