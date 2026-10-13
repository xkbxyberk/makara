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

    /// Text on a SwiftUI screen (not the web page).
    @discardableResult
    private func native(_ text: String, timeout: TimeInterval = 30) -> XCUIElement {
        let element = app.windows.firstMatch.staticTexts
            .matching(NSPredicate(format: "value BEGINSWITH %@ OR label BEGINSWITH %@", text, text)).firstMatch
        XCTAssertTrue(element.waitForExistence(timeout: timeout), "the screen never showed “\(text)”")
        return element
    }

    private func element(_ identifier: String) -> XCUIElement {
        app.windows.firstMatch.descendants(matching: .any)[identifier].firstMatch
    }

    /// A call to the test server (port 8789, fixture mode): what the extension or another
    /// screen would do behind this one's back.
    @discardableResult
    private func api(_ method: String, _ path: String, _ body: [String: Any]? = nil) throws -> [String: Any] {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8789/\(path)")!)
        request.httpMethod = method
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let answered = expectation(description: "\(method) \(path)")
        var reply: [String: Any] = [:]
        URLSession.shared.dataTask(with: request) { data, _, _ in
            reply = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
            answered.fulfill()
        }.resume()
        wait(for: [answered], timeout: 30)
        return reply
    }

    /// What the extension's one-click download does: `/api/quick`.
    private func startDownload() throws -> String {
        let reply = try api("POST", "api/quick", ["url": "https://example.test/local-media", "rule": ["kind": "video"]])
        let id = ((reply["job"] as? [String: Any])?["id"] as? String) ?? ""
        XCTAssertFalse(id.isEmpty, "the test server queued nothing")
        return id
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
        native("Henüz bir şey incelemedin")
        screenshot("native-inspect-light")

        sidebar("Sistem").click()
        native("JavaScript çalıştırıcı")
        XCTAssertEqual(app.windows.firstMatch.title, "Sistem")
        XCTAssertFalse(app.webViews.firstMatch.exists, "Sistem is a native screen now")
        screenshot("native-doctor-light")

        app.typeKey("3", modifierFlags: .command)  // Git > Kütüphane
        XCTAssertTrue(app.windows["Kütüphane"].waitForExistence(timeout: 10))
    }

    func testDarkAppearance() {
        app.launchEnvironment["VD_APPEARANCE"] = "dark"
        app.launch()
        native("Henüz bir şey incelemedin")
        screenshot("native-inspect-dark")
        sidebar("Sistem").click()
        native("JavaScript çalıştırıcı")
        screenshot("native-doctor-dark")
        sidebar("İndirmeler").click()
        native("Henüz indirme yok")
        screenshot("native-queue-empty-dark")
    }

    func testSettingsOpenInTheirOwnWindowFromTheAppMenu() {
        app.launch()
        native("Henüz bir şey incelemedin")
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

    func testTheDoctorIsNativeAndSaysWhatEachToolNeeds() throws {
        app.launch()
        sidebar("Sistem").click()
        for check in ["yt_dlp", "js_runtime", "ffmpeg", "safari_session"] {
            XCTAssertTrue(element("doctor.check.\(check)").waitForExistence(timeout: 30), "no \(check) row")
        }
        // The test server never has a Safari session (never Berk's): it says how to get one,
        // and there is nothing to grant Full Disk Access for.
        native("Safari’nin çerez dosyası bulunamadı")
        XCTAssertFalse(app.buttons["Tam Disk Erişimi ayarlarını aç"].exists)
        XCTAssertTrue(app.buttons["yt-dlp’yi güncelle"].exists)
        native("H.264 kodlama (libx264)")
        // Turning the session off elsewhere shows after a refresh, with a way to the setting:
        // the refresh really asks again. Written to the test's own settings file, which the
        // server reads on every check (PUT /api/settings would refuse this runner's download
        // folder: it sits under ~/Library/Containers, and the sandboxed runner cannot use /tmp).
        let file = scratch.appending(path: "data/settings.json")
        try JSONSerialization.data(withJSONObject: ["safari_login": false]).write(to: file)
        XCTAssertEqual(try api("GET", "api/settings")["safari_login"] as? Bool, false)
        element("doctor.refresh").click()
        native("Kapalı: giriş isteyen videolar")
        XCTAssertFalse(app.windows.firstMatch.staticTexts["Safari’nin çerez dosyası bulunamadı. Safari’yi bir kez açıp YouTube’a giriş yap."].exists)
        XCTAssertTrue(app.buttons["Ayarlar’ı aç"].exists, "no way to the setting")
    }

    func testTheQueueIsNativeAndFollowsADownload() throws {
        app.launch()
        native("Henüz bir şey incelemedin")
        sidebar("İndirmeler").click()
        native("Henüz indirme yok")
        XCTAssertEqual(app.windows.firstMatch.title, "İndirmeler")
        screenshot("native-queue-empty-light")

        _ = try startDownload()
        native("Local test clip")
        XCTAssertTrue(app.windows.firstMatch.staticTexts["Tamamlandı"].waitForExistence(timeout: 60), "the download never finished")
        native("Arşiv MKV")
        let reveal = app.buttons["Finder’da göster"].firstMatch
        XCTAssertTrue(reveal.exists, "a finished download offers its file")
        screenshot("native-queue-done-light")

        // A file moved away since: the row says so instead of failing silently.
        let downloads = scratch.appending(path: "downloads")
        let files = FileManager.default.enumerator(at: downloads, includingPropertiesForKeys: nil)?
            .compactMap { $0 as? URL }.filter { $0.pathExtension == "mkv" } ?? []
        let file = try XCTUnwrap(files.first, "no downloaded file")
        try FileManager.default.removeItem(at: file)
        reveal.click()
        native("Dosya yerinde değil")

        // Removing it from the list leaves the list empty again.
        app.buttons["Listeden kaldır"].firstMatch.click()
        native("Henüz indirme yok")
    }

    private func inspect(_ link: String) {
        let field = app.textFields["inspect.url"]
        XCTAssertTrue(field.waitForExistence(timeout: 30), "no link field")
        field.click()
        field.typeKey("a", modifierFlags: .command)
        field.typeText(link + "\r")
    }

    func testInspectingAndDownloadingIsNative() {
        app.launch()
        native("Henüz bir şey incelemedin")
        XCTAssertFalse(app.webViews.firstMatch.exists, "İncele is a native screen now")
        screenshot("native-inspect-empty-light")

        inspect("https://example.test/local-media")
        native("Local test clip")
        XCTAssertTrue(element("quick").waitForExistence(timeout: 10), "no quick choices")
        native("Tahmini boyut")
        let download = app.buttons["download.submit"]
        // İndir waits for the plan of exactly this selection.
        XCTAssertTrue(download.waitForExistence(timeout: 10))
        let enabled = NSPredicate(format: "isEnabled == true")
        expectation(for: enabled, evaluatedWith: download)
        waitForExpectations(timeout: 15)
        screenshot("native-inspected-local-light")

        // Audio only, in the picker: no video section, a format (and a quality) instead.
        app.buttons["download.picker"].click()
        native("Görüntü")
        app.radioButtons["Sadece ses"].firstMatch.click()
        native("Ses biçimi")
        XCTAssertFalse(element("picker").staticTexts["Görüntü"].exists)
        app.radioButtons["Arşiv MKV"].firstMatch.click()
        XCTAssertTrue(download.waitForExistence(timeout: 5))
        expectation(for: enabled, evaluatedWith: download)
        waitForExpectations(timeout: 15)

        download.click()
        native("Kuyruğa eklendi.")
        app.buttons["İndirmeleri aç"].click()
        XCTAssertTrue(app.windows["İndirmeler"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.windows.firstMatch.staticTexts["Tamamlandı"].waitForExistence(timeout: 60), "the download never finished")

        // Back on İncele the panel is as it was left: queued, and not queued twice.
        sidebar("İncele").click()
        native("Kuyruğa eklendi.")
        XCTAssertFalse(app.buttons["download.submit"].isEnabled, "the same selection could be queued again")
    }

    /// The opt-in clipboard watcher's offer is native and shows on any screen.
    func testACopiedLinkIsOfferedAndInspected() throws {
        app.launch()
        sidebar("Sistem").click()
        native("JavaScript çalıştırıcı")
        try api("POST", "api/test/clipboard", ["url": "https://example.test/local-media"])
        XCTAssertTrue(element("clipboard.offer").waitForExistence(timeout: 15), "no clipboard offer")
        XCTAssertFalse(app.webViews.firstMatch.exists)
        element("clipboard.offer").buttons["İncele"].click()
        native("Local test clip")
        XCTAssertTrue(app.windows["İncele"].waitForExistence(timeout: 10))
        XCTAssertFalse(element("clipboard.offer").exists, "the offer stayed after it was taken")
    }

    func testTheTrackPickerAndEveryTrackOfAMultiAudioVideo() {
        app.launch()
        inspect("https://www.youtube.com/watch?v=0e3GPea1Tyg")  // a recorded answer: no network
        native("$456,000 Squid Game In Real Life!")
        native("Ses parçaları")
        native("Orijinal")
        native("Dublaj")
        screenshot("native-inspected-multi-audio-light")
        app.buttons["download.picker"].click()
        XCTAssertTrue(element("picker").waitForExistence(timeout: 10), "no track picker")
        native("Görüntü")
        native("Ekler")
        screenshot("native-track-picker-light")
    }

    /// ⌘V outside the field inspects the copied link, as on the web page.
    func testPastingAnywhereInspectsTheCopiedLink() {
        app.launch()
        let empty = native("Henüz bir şey incelemedin")
        // The pasteboard is Berk's: whatever he had copied goes back afterwards.
        let board = NSPasteboard.general
        let saved = board.pasteboardItems?.map { item in
            item.types.reduce(into: [NSPasteboard.PasteboardType: Data]()) { $0[$1] = item.data(forType: $1) }
        } ?? []
        addTeardownBlock {
            board.clearContents()
            board.writeObjects(saved.map { types in
                let item = NSPasteboardItem()
                for (type, data) in types { item.setData(data, forType: type) }
                return item
            })
        }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString("https://example.test/local-media", forType: .string)
        empty.click()
        app.typeKey("v", modifierFlags: .command)
        native("Local test clip")
        XCTAssertEqual(app.textFields["inspect.url"].value as? String, "https://example.test/local-media")
    }

    func testABadLinkIsExplainedWithARetry() {
        app.launch()
        inspect("not a link")
        native("Bu bir bağlantı değil")
        XCTAssertTrue(app.buttons["Tekrar dene"].exists)
    }

    func testTheURLSchemeInspectsALink() {
        app.launch()
        native("Henüz bir şey incelemedin")
        sidebar("Sistem").click()
        native("JavaScript çalıştırıcı")
        let link = URL(string: "videodownloader://inspect?url=https%3A%2F%2Fexample.test%2Flocal-media")!
        NSWorkspace.shared.open(link)
        native("Local test clip")
        XCTAssertTrue(app.windows["İncele"].waitForExistence(timeout: 10), "the sidebar did not follow to İncele")
        screenshot("native-inspected-light")
    }

    /// A closed app opened by a link (a Safari click, a Dock drop): the link arrives before the
    /// backend and the page exist, and must still be inspected (it used to be lost).
    func testALinkHandedOverAtLaunchIsInspectedOnceThePageIsReady() {
        app.launchEnvironment["VD_OPEN_AT_LAUNCH"] = "videodownloader://inspect?url=https%3A%2F%2Fexample.test%2Flocal-media"
        app.launch()
        native("Local test clip")
        XCTAssertTrue(app.windows["İncele"].exists)
    }

    func testAScreenAskedForAtLaunchIsTheOneShown() {
        app.launchEnvironment["VD_OPEN_AT_LAUNCH"] = "videodownloader://show?route=doctor"
        app.launch()
        native("JavaScript çalıştırıcı")
        XCTAssertTrue(app.windows["Sistem"].waitForExistence(timeout: 10), "the page pulled the window back")
    }

    /// A .webloc opened with the app takes the same path as a link dropped on the Dock icon
    /// (`application(_:open:)`).
    func testAWebLinkFileOpenedWithTheAppIsInspected() throws {
        app.launch()
        native("Henüz bir şey incelemedin")
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
        native("Local test clip")
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
        native("Henüz bir şey incelemedin")
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
