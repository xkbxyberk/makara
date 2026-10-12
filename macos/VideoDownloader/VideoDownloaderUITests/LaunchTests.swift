import XCTest

/// N0 spike: XCUITest can launch the app from the command line, find its window, act on it and
/// save a screenshot. The real screen scenarios arrive with the SwiftUI screens (N2+).
final class LaunchTests: XCTestCase {
    func testLaunchShowsTheWindowAndQuitsWhenItCloses() throws {
        let app = XCUIApplication()
        app.launch()

        let window = app.windows.firstMatch
        XCTAssertTrue(window.waitForExistence(timeout: 10), "the main window never appeared")

        let shot = XCTAttachment(screenshot: window.screenshot())
        shot.name = "launch"
        shot.lifetime = .keepAlways
        add(shot)

        // Driving the app: closing the last window quits it (applicationShouldTerminateAfterLastWindowClosed).
        // The packager's template menu has no ⌘W; the real menus arrive with the SwiftUI shell (N2).
        window.buttons[XCUIIdentifierCloseWindow].click()
        XCTAssertTrue(app.wait(for: .notRunning, timeout: 10), "the app did not quit after its last window closed")
    }
}
