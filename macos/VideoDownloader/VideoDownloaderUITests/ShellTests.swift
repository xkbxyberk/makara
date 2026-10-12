import AppKit
import XCTest

/// The native shell against the real backend in fixture mode: no network, its own port, its
/// own data folders and log -- never Berk's.
final class ShellTests: XCTestCase {
    private var app: XCUIApplication!
    private var scratch: URL!

    override func setUpWithError() throws {
        continueAfterFailure = false
        scratch = FileManager.default.temporaryDirectory.appending(path: "vd-uitest-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: scratch, withIntermediateDirectories: true)
        app = XCUIApplication()
        app.launchEnvironment = [
            "VD_PORT": "8789",
            "VD_FIXTURE_MODE": "1",
            "VD_DATA_DIR": scratch.appending(path: "data").path,
            "VD_DOWNLOAD_DIR": scratch.appending(path: "downloads").path,
            "VD_LOG_FILE": scratch.appending(path: "backend.log").path,
            // Screenshots say "light" or "dark"; never whatever this Mac happens to be set to.
            "VD_APPEARANCE": "light",
        ]
    }

    override func tearDownWithError() throws {
        app.terminate()
        try? FileManager.default.removeItem(at: scratch)
    }

    private func screenshot(_ name: String) {
        let shot = XCTAttachment(screenshot: app.windows.firstMatch.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }

    @discardableResult
    private func page(_ text: String, timeout: TimeInterval = 30) -> XCUIElement {
        // Web text is exposed as the element's value, not its label.
        let element = app.webViews.staticTexts
            .matching(NSPredicate(format: "value BEGINSWITH %@ OR label BEGINSWITH %@", text, text)).firstMatch
        XCTAssertTrue(element.waitForExistence(timeout: timeout), "the page never showed “\(text)”")
        return element
    }

    private func sidebar(_ title: String) -> XCUIElement {
        let row = app.outlines.staticTexts[title]
        XCTAssertTrue(row.waitForExistence(timeout: 30), "no sidebar row “\(title)”")
        return row
    }

    func testTheShellShowsTheSidebarAndEmbeddedScreens() {
        app.launch()
        _ = sidebar("İncele")
        for title in ["İndirmeler", "Kütüphane", "Stüdyo", "Sistem"] { _ = sidebar(title) }
        XCTAssertFalse(app.outlines.staticTexts["Ayarlar"].exists, "Settings belongs in its own window")
        page("Henüz bir şey incelemedin")
        screenshot("native-inspect-light")

        sidebar("Sistem").click()
        page("JavaScript çalıştırıcı")
        XCTAssertEqual(app.windows.firstMatch.title, "Sistem")
        screenshot("native-doctor-light")

        app.typeKey("3", modifierFlags: .command)  // Git > Kütüphane
        XCTAssertTrue(app.windows["Kütüphane"].waitForExistence(timeout: 10))
    }

    func testDarkAppearance() {
        app.launchEnvironment["VD_APPEARANCE"] = "dark"
        app.launch()
        page("Henüz bir şey incelemedin")
        screenshot("native-inspect-dark")
        sidebar("Sistem").click()
        page("JavaScript çalıştırıcı")
        screenshot("native-doctor-dark")
    }

    func testSettingsOpenInTheirOwnWindowFromTheAppMenu() {
        app.launch()
        page("Henüz bir şey incelemedin")
        // VideoDownloader > Ayarlar… (the system's own item, which carries ⌘,).
        let item = app.menuBars.menuItems["Ayarlar…"]
        XCTAssertTrue(item.waitForExistence(timeout: 10))
        item.click()
        page("İndirme klasörü")
        let settings = app.windows["VideoDownloader Ayarları"]
        XCTAssertTrue(settings.waitForExistence(timeout: 10), "no Settings window")
        // The window only -- never the whole screen, which shows whatever else Berk has open.
        let shot = XCTAttachment(screenshot: settings.screenshot())
        shot.name = "native-settings-light"
        shot.lifetime = .keepAlways
        add(shot)
    }

    func testTheURLSchemeInspectsALink() {
        app.launch()
        page("Henüz bir şey incelemedin")
        sidebar("Sistem").click()
        page("JavaScript çalıştırıcı")
        let link = URL(string: "videodownloader://inspect?url=https%3A%2F%2Fexample.test%2Flocal-media")!
        NSWorkspace.shared.open(link)
        page("Local test clip")
        XCTAssertTrue(app.windows["İncele"].waitForExistence(timeout: 10), "the sidebar did not follow to İncele")
        screenshot("native-inspected-light")
    }

    /// A closed app opened by a link (a Safari click, a Dock drop): the link arrives before the
    /// backend and the page exist, and must still be inspected (it used to be lost).
    func testALinkHandedOverAtLaunchIsInspectedOnceThePageIsReady() {
        app.launchEnvironment["VD_OPEN_AT_LAUNCH"] = "videodownloader://inspect?url=https%3A%2F%2Fexample.test%2Flocal-media"
        app.launch()
        page("Local test clip")
        XCTAssertTrue(app.windows["İncele"].exists)
    }

    func testAScreenAskedForAtLaunchIsTheOneShown() {
        app.launchEnvironment["VD_OPEN_AT_LAUNCH"] = "videodownloader://show?route=doctor"
        app.launch()
        page("JavaScript çalıştırıcı")
        XCTAssertTrue(app.windows["Sistem"].waitForExistence(timeout: 10), "the page pulled the window back")
    }

    /// A .webloc opened with the app takes the same path as a link dropped on the Dock icon
    /// (`application(_:open:)`).
    func testAWebLinkFileOpenedWithTheAppIsInspected() throws {
        app.launch()
        page("Henüz bir şey incelemedin")
        let webloc = scratch.appending(path: "clip.webloc")
        let plist = try PropertyListSerialization.data(fromPropertyList: ["URL": "https://example.test/local-media"],
                                                       format: .xml, options: 0)
        try plist.write(to: webloc)
        let appURL = try XCTUnwrap(NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.berkakbay.VideoDownloader"))
        let opened = expectation(description: "handed to the app")
        NSWorkspace.shared.open([webloc], withApplicationAt: appURL, configuration: NSWorkspace.OpenConfiguration()) { _, _ in
            opened.fulfill()
        }
        wait(for: [opened], timeout: 10)
        page("Local test clip")
    }

    func testABackendThatCannotStartIsExplainedWithARetry() {
        app.launchEnvironment["VD_PROJECT_ROOT"] = "/nonexistent"
        app.launchEnvironment["VD_PORT"] = "8791"
        app.launch()
        XCTAssertTrue(app.staticTexts["Uygulama sunucusu başlatılamadı"].waitForExistence(timeout: 30))
        XCTAssertTrue(app.buttons["Yeniden dene"].exists)
        XCTAssertTrue(app.buttons["Günlüğü Finder’da göster"].exists)
        screenshot("native-backend-failed-light")
    }

    func testClosingTheWindowQuitsAndStopsTheBackend() {
        app.launch()
        page("Henüz bir şey incelemedin")
        let started = Date()
        app.windows.firstMatch.buttons[XCUIIdentifierCloseWindow].click()
        XCTAssertTrue(app.wait(for: .notRunning, timeout: 30), "the app did not quit")
        // A clean stop, not the 15 s SIGKILL fallback (an open event stream once forced that).
        XCTAssertLessThan(Date().timeIntervalSince(started), 8)
        // Its server went with it: the port no longer answers.
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8789/api/health")!)
        request.timeoutInterval = 2
        let gone = expectation(description: "server gone")
        URLSession.shared.dataTask(with: request) { _, response, _ in
            if response == nil { gone.fulfill() }
        }.resume()
        wait(for: [gone], timeout: 5)
    }
}
