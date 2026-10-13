import Foundation
import Testing
@testable import VideoDownloaderKit

/// A stand-in for the backend's settings: it refuses any download folder under /Library (as the
/// real one does for ~/Library) and the clipboard watcher when told to, and keeps the rest.
final class SettingsServer: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var stored: [String: Any] = [:]
    nonisolated(unsafe) static var refuseClipboard = false
    nonisolated(unsafe) static var puts: [[String: Any]] = []

    static func reset() {
        stored = ["download_dir": "/Users/b/Movies/VD", "filename_template": "%(title)s", "concurrency": 2,
                  "default_mode": "mkv", "clipboard_watch": false, "notifications": true, "safari_login": true,
                  "default_filename_template": "%(title)s"]
        refuseClipboard = false
        puts = []
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        var status = 200
        var body: [String: Any] = Self.stored
        if request.httpMethod == "PUT", let data = request.httpBody ?? request.httpBodyStream.map(Self.read),
           let sent = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            Self.puts.append(sent)
            if (sent["download_dir"] as? String ?? "").hasPrefix("/Library") {
                status = 400
                body = ["error": ["code": "DOWNLOAD_DIR_UNSAFE"]]
            } else if Self.refuseClipboard, sent["clipboard_watch"] as? Bool == true {
                status = 400
                body = ["error": ["code": "SETTINGS_UNAVAILABLE"]]
            } else {
                Self.stored.merge(sent) { $1 }
                body = Self.stored
            }
        }
        let data = try! JSONSerialization.data(withJSONObject: body)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                                              headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}

    static func read(_ stream: InputStream) -> Data {
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let n = stream.read(&buffer, maxLength: buffer.count)
            if n <= 0 { break }
            data.append(buffer, count: n)
        }
        return data
    }
}

@MainActor
@Suite(.serialized)
struct PreferencesTests {
    static func preferences() -> Preferences {
        SettingsServer.reset()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [SettingsServer.self]
        let session = URLSession(configuration: configuration)
        return Preferences(client: { APIClient(port: 1, session: session) })
    }

    @Test func aRefusedFolderDoesNotTakeLaterSwitchesWithIt() async {
        let preferences = Self.preferences()
        await preferences.load()
        preferences.draft?.downloadDir = "/Library/Nope"
        preferences.commitText()
        await preferences.settle()
        #expect(preferences.failure?.code == "DOWNLOAD_DIR_UNSAFE")
        #expect(preferences.draft?.downloadDir == "/Library/Nope")  // the typed folder stays, unsaved
        // A switch afterwards is sent on its own, from what is saved: it is applied.
        preferences.apply({ $0.notifications = false }, springBack: true)
        await preferences.settle()
        #expect(preferences.failure == nil)
        #expect(SettingsServer.stored["notifications"] as? Bool == false)
        #expect(SettingsServer.stored["download_dir"] as? String == "/Users/b/Movies/VD")
        #expect(preferences.draft?.downloadDir == "/Library/Nope")  // still what Berk typed
    }

    @Test func aRefusedSwitchSpringsBackEvenWhenAnotherChangeFollowsAtOnce() async {
        let preferences = Self.preferences()
        await preferences.load()
        SettingsServer.refuseClipboard = true
        preferences.apply({ $0.clipboardWatch = true }, springBack: true)
        preferences.apply({ $0.concurrency = 4 }, springBack: true)  // before the first answered
        #expect(preferences.draft?.clipboardWatch == true)  // shown at once
        await preferences.settle()
        #expect(preferences.draft?.clipboardWatch == false)  // refused: back to what is in effect
        #expect(preferences.draft?.concurrency == 4)
        #expect(SettingsServer.stored["concurrency"] as? Int == 4)
        #expect(SettingsServer.puts.count == 2)  // in order, none skipped
    }

    @Test func theServersFolderIsShownOnceApplied() async {
        let preferences = Self.preferences()
        await preferences.load()
        preferences.apply({ $0.downloadDir = "/Users/b/Movies/New" }, springBack: false)
        await preferences.settle()
        #expect(preferences.saved?.downloadDir == "/Users/b/Movies/New")
        #expect(preferences.dirty == false)
    }
}
