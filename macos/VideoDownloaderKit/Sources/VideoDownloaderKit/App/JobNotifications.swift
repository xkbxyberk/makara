import Foundation

/// When a job deserves a system notification: it just finished or failed (a transition seen
/// live, never a job that was already done in the first snapshot) and the app is not in front.
public enum JobNotification: Equatable, Sendable {
    case done(title: String)
    case failed(title: String)

    public static func `for`(previous: Job?, current: Job, appIsActive: Bool, enabled: Bool) -> JobNotification? {
        guard enabled, !appIsActive, let previous, previous.status != current.status else { return nil }
        let title = current.title ?? current.sourceUrl ?? ""
        switch current.status {
        case .done: return .done(title: title)
        case .failed: return .failed(title: title)
        default: return nil
        }
    }
}
