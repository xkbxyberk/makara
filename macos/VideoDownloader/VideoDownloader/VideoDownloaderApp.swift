import AppKit
import SafariServices
import SwiftUI
import VideoDownloaderKit

let extensionBundleIdentifier = "com.berkakbay.VideoDownloader.Extension"

@main
struct VideoDownloaderApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        // One window, not a WindowGroup: a link handed to the app must not open a second one.
        Window(L("app.name"), id: "main") {
            RootView(model: delegate.model)
                .frame(minWidth: 760, minHeight: 520)
        }
        .defaultSize(width: 1180, height: 820)
        .commands { AppCommands(model: delegate.model) }

        Settings {
            SettingsView(model: delegate.model)
        }

        // On by default (Berk): the app, and with it the extension's backend, outlives its window.
        MenuBarExtra(isInserted: Binding(get: { delegate.model.shell.menuBarIcon },
                                         set: { delegate.model.shell.setMenuBarIcon($0) })) {
            MenuBarView(model: delegate.model)
        } label: {
            MenuBarLabel(model: delegate.model)
        }
        .menuBarExtraStyle(.window)
    }
}

/// The menu bar glyph, with the number of running downloads beside it.
struct MenuBarLabel: View {
    let model: AppModel

    var body: some View {
        Image("MenuBarIcon")  // the app icon's mark, a template (macos/design/menubar.svg)
        // While downloading: how far, then (several at once) how many.
        if let fraction = model.overallProgress {
            Text(model.activeCount > 1 ? "\(Int((fraction * 100).rounded()))% · \(model.activeCount)"
                                       : "\(Int((fraction * 100).rounded()))%")
                .monospacedDigit()
        } else if model.activeCount > 0 {
            Text("\(model.activeCount)")
        }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let model = AppModel()
    private var shuttingDown = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        // `--print-extension-state`: report whether Safari has the extension enabled, then quit.
        // Only the containing app may ask Safari this, so scripts and tests go through here.
        if CommandLine.arguments.contains("--print-extension-state") {
            SFSafariExtensionManager.getStateOfSafariExtension(withIdentifier: extensionBundleIdentifier) { state, error in
                let line = error.map { "error: \($0.localizedDescription)" } ?? "enabled: \(state?.isEnabled ?? false)"
                FileHandle.standardOutput.write(Data((line + "\n").utf8))
                // Nothing was started in this mode: leave at once (a normal terminate goes through
                // the backend shutdown below, and waited for good when another copy was running).
                exit(0)
            }
            return
        }
        model.shell.applyDock()
        // Started by the login item: stay in the menu bar, no window (when there is a menu bar
        // item to come back through).
        if Shell.launchedAsLoginItem, model.shell.menuBarIcon {
            DispatchQueue.main.async {
                for window in NSApp.windows where window.isVisible && window.styleMask.contains(.titled) { window.close() }
            }
        }
        // UI tests take light and dark screenshots without touching the system setting.
        switch ProcessInfo.processInfo.environment["VD_APPEARANCE"] {
        case "dark": NSApp.appearance = NSAppearance(named: .darkAqua)
        case "light": NSApp.appearance = NSAppearance(named: .aqua)
        default: break
        }
        // UI tests: a link handed over while the app is still starting (what a Safari click or
        // a Dock drop does to a closed app), without going through LaunchServices.
        if let raw = ProcessInfo.processInfo.environment["VD_OPEN_AT_LAUNCH"], let url = URL(string: raw),
           let incoming = IncomingURL.parse(url) {
            model.handle(incoming)
        }
        Task {
            await model.start()
            // Not under tests or development (a data folder is named): they would ask every time.
            if model.isReady, ProcessInfo.processInfo.environment["VD_DATA_DIR"] == nil {
                model.shell.askAboutLoginOnce()
            }
        }
    }

    /// `videodownloader://…`, a link dropped on the Dock icon, a .webloc opened with the app.
    func application(_ application: NSApplication, open urls: [URL]) {
        for url in urls {
            if let incoming = IncomingURL.parse(url) { model.handle(incoming) }
        }
    }

    /// With the menu bar item the app keeps running (the Safari extension needs its backend).
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        !model.shell.keepsRunningWithoutWindow
    }

    /// Quit waits for the backend to stop its workers cleanly (it gets SIGTERM, then SIGKILL).
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard !shuttingDown else { return .terminateLater }
        shuttingDown = true
        Task {
            await model.shutdown()
            sender.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }
}
