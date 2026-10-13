import AppKit
import UserNotifications

/// The buttons on a download's notification (P6b): a finished one offers "Oynat" and "Finder'da
/// göster", a failed one "Tekrar dene". Clicking the notification itself shows İndirmeler.
@MainActor
final class NotificationActions: NSObject, UNUserNotificationCenterDelegate {
    static let done = "vd.done"
    static let failed = "vd.failed"
    static let play = "vd.play"
    static let reveal = "vd.reveal"
    static let retry = "vd.retry"

    weak var model: AppModel?

    func install() {
        let center = UNUserNotificationCenter.current()
        center.setNotificationCategories([
            UNNotificationCategory(identifier: Self.done, actions: [
                UNNotificationAction(identifier: Self.play, title: L("notify.play"), options: [.foreground]),
                UNNotificationAction(identifier: Self.reveal, title: L("notify.reveal"), options: [.foreground]),
            ], intentIdentifiers: []),
            UNNotificationCategory(identifier: Self.failed, actions: [
                UNNotificationAction(identifier: Self.retry, title: L("notify.retry"), options: []),
            ], intentIdentifiers: []),
        ])
        center.delegate = self
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        let action = response.actionIdentifier
        guard let jobId = response.notification.request.content.userInfo["job"] as? String else { return }
        await MainActor.run { handle(action, jobId: jobId) }
    }

    private func handle(_ action: String, jobId: String) {
        guard let model else { return }
        let client = model.backend.client
        switch action {
        case Self.play:
            // A file this app wrote, opened in the default player (there is no player in the app).
            if let path = model.jobs[jobId]?.outputFiles.first, FileManager.default.fileExists(atPath: path) {
                NSWorkspace.shared.open(URL(fileURLWithPath: path))
            }
        case Self.reveal:
            Task { try? await client.reveal(job: jobId, file: 0) }
        case Self.retry:
            Task { try? await client.retry(job: jobId) }
        default:
            model.route = .download
            NSApp.activate()
            NSApp.windows.first { $0.canBecomeMain }?.makeKeyAndOrderFront(nil)
        }
    }
}
