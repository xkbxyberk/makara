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
        Task { await model.start() }
    }

    /// `videodownloader://…`, a link dropped on the Dock icon, a .webloc opened with the app.
    func application(_ application: NSApplication, open urls: [URL]) {
        for url in urls {
            if let incoming = IncomingURL.parse(url) { model.handle(incoming) }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

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
