import Cocoa
import SafariServices

@main
class AppDelegate: NSObject, NSApplicationDelegate {

    func applicationDidFinishLaunching(_ notification: Notification) {
        // `--print-extension-state`: report whether Safari has the extension enabled, then quit.
        // Only the containing app may ask Safari this, so scripts and tests go through here.
        if CommandLine.arguments.contains("--print-extension-state") {
            SFSafariExtensionManager.getStateOfSafariExtension(withIdentifier: extensionBundleIdentifier) { state, error in
                let line = error.map { "error: \($0.localizedDescription)" } ?? "enabled: \(state?.isEnabled ?? false)"
                FileHandle.standardOutput.write(Data((line + "\n").utf8))
                DispatchQueue.main.async { NSApplication.shared.terminate(nil) }
            }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }

}
