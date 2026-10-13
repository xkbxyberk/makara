import AppKit
import Observation
import ServiceManagement

/// How the app lives on this Mac (P4, Berk 2026-10-14): a menu bar item (on by default), the
/// Dock icon, and starting at login so the Safari extension finds the app running. Kept on this
/// Mac (LocalStore), not in the backend's settings: none of it concerns the server.
@MainActor
@Observable
public final class Shell {
    public private(set) var menuBarIcon = true
    public private(set) var showInDock = true
    public private(set) var loginStatus: SMAppService.Status = .notRegistered
    /// Why the last start-at-login change failed, as the system said it.
    public private(set) var loginError: String?

    /// Whether the one-time "start at login?" question was asked.
    public private(set) var askedAboutLogin = false

    struct Stored: Codable {
        var menuBarIcon = true
        var showInDock = true
        var askedAboutLogin: Bool? = false
    }

    static let key = "vd-shell"
    @ObservationIgnored private let store: LocalStore

    public init(store: LocalStore) {
        self.store = store
        if let data = store.data(Self.key), let stored = try? JSONDecoder().decode(Stored.self, from: data) {
            menuBarIcon = stored.menuBarIcon
            // Never neither: an app with no Dock icon and no menu bar item cannot be reached.
            showInDock = stored.showInDock || !stored.menuBarIcon
            askedAboutLogin = stored.askedAboutLogin ?? false
        }
        refreshLogin()
    }

    /// Closing the window keeps the app (and so the extension's backend) running only when it
    /// can still be reached from the menu bar.
    public var keepsRunningWithoutWindow: Bool { menuBarIcon }

    public func setMenuBarIcon(_ on: Bool) {
        menuBarIcon = on
        if !on, !showInDock { setShowInDock(true) }
        save()
    }

    public func setShowInDock(_ on: Bool) {
        showInDock = on || !menuBarIcon
        save()
        applyDock()
    }

    /// The Dock icon follows the setting; without it the app is an "accessory", like a menu bar
    /// utility, and its windows still open on top.
    public func applyDock() {
        let policy: NSApplication.ActivationPolicy = showInDock ? .regular : .accessory
        guard NSApp.activationPolicy() != policy else { return }
        NSApp.setActivationPolicy(policy)
        if policy == .accessory { NSApp.activate() }  // keep the window that changed it in front
    }

    // ---- start at login ---------------------------------------------------------------------

    /// On, or waiting for Berk's approval in System Settings > General > Login Items.
    public var launchAtLogin: Bool { loginStatus == .enabled || loginStatus == .requiresApproval }

    public func setLaunchAtLogin(_ on: Bool) {
        do {
            if on { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
            loginError = nil
        } catch {
            loginError = error.localizedDescription
        }
        refreshLogin()
    }

    public func refreshLogin() {
        loginStatus = SMAppService.mainApp.status
    }

    public func openLoginItemsSettings() {
        SMAppService.openSystemSettingsLoginItems()
    }

    /// Whether this launch was the login item's (the window then stays closed when the menu
    /// bar item is there). Valid while the launch's "open application" event is being handled.
    public static var launchedAsLoginItem: Bool {
        guard let event = NSAppleEventManager.shared().currentAppleEvent,
              event.eventID == AEEventID(kAEOpenApplication) else { return false }
        return event.paramDescriptor(forKeyword: AEKeyword(keyAEPropData))?.enumCodeValue == OSType(keyAELaunchedAsLogInItem)
    }

    /// Asked once, after the first start (Berk's plan: on, but never without asking).
    public func askAboutLoginOnce() {
        guard !askedAboutLogin else { return }
        askedAboutLogin = true
        save()
        guard !launchAtLogin else { return }
        let alert = NSAlert()
        alert.messageText = L("shell.askLogin.title")
        alert.informativeText = L("shell.askLogin.body")
        alert.addButton(withTitle: L("shell.askLogin.yes"))
        alert.addButton(withTitle: L("shell.askLogin.no"))
        if alert.runModal() == .alertFirstButtonReturn { setLaunchAtLogin(true) }
    }

    private func save() {
        let stored = Stored(menuBarIcon: menuBarIcon, showInDock: showInDock, askedAboutLogin: askedAboutLogin)
        if let data = try? JSONEncoder().encode(stored) {
            store.set(data, Self.key)
        }
    }
}
