import Foundation
import Testing
@testable import VideoDownloaderRelay

struct RelayTests {
    func request(_ message: [String: Any]) -> URLRequest? {
        if case .success(.http(let request)) = Relay.action(for: message) { return request }
        return nil
    }

    @Test func theAllowedCallsBecomeRequestsTo127001() throws {
        let supports = try #require(request(["type": "api", "path": "api/supports", "query": ["url": "https://www.youtube.com/watch?v=a&b=c"]]))
        #expect(supports.httpMethod == "GET")
        #expect(supports.url?.host() == "127.0.0.1" && supports.url?.port == 8787)
        #expect(URLComponents(url: supports.url!, resolvingAgainstBaseURL: false)?.queryItems == [URLQueryItem(name: "url", value: "https://www.youtube.com/watch?v=a&b=c")])
        let quick = try #require(request(["type": "api", "method": "POST", "path": "api/quick", "body": ["url": "https://x.test/v", "rule": ["kind": "video"]]]))
        #expect(quick.httpMethod == "POST")
        let body = try JSONSerialization.jsonObject(with: try #require(quick.httpBody)) as? [String: Any]
        #expect(body?["url"] as? String == "https://x.test/v")
        #expect(request(["type": "api", "path": "api/jobs"]) != nil)
        #expect(request(["type": "api", "path": "api/health"]) != nil)
        #expect(request(["type": "api", "path": "api/extension"]) != nil)  // how to offer a video
        #expect(request(["type": "api", "method": "POST", "path": "api/inspect", "body": ["url": "https://x.test/v"]]) != nil)
    }

    @Test func everythingElseIsRefused() {
        let refused: [[String: Any]] = [
            ["type": "api", "method": "POST", "path": "api/library/abc/trash", "body": [:]],
            ["type": "api", "method": "POST", "path": "api/system/update-ytdlp", "body": [:]],
            ["type": "api", "method": "POST", "path": "api/system/pick-folder", "body": [:]],
            ["type": "api", "method": "DELETE", "path": "api/jobs"],
            ["type": "api", "method": "PUT", "path": "api/settings"],
            ["type": "api", "path": "api/settings"],  // the extension reads only api/extension
            ["type": "api", "path": "api/../api/settings"],
            ["type": "api", "path": "/api/health"],
            ["type": "api", "path": "api/jobs", "query": ["x": "1"]],
            ["type": "api", "path": "api/supports", "query": ["url": "u", "extra": "1"]],
            ["type": "api", "method": "GET", "path": "api/quick"],
            ["type": "shell", "command": "rm -rf /"],
            [:],
        ]
        for message in refused {
            #expect(Relay.action(for: message) == .failure(.notAllowed), "\(message)")
        }
    }

    @Test func aPostNeedsASmallJSONObjectBody() {
        #expect(Relay.action(for: ["type": "api", "method": "POST", "path": "api/quick"]) == .failure(.badBody))
        let huge = String(repeating: "x", count: 70_000)
        #expect(Relay.action(for: ["type": "api", "method": "POST", "path": "api/quick", "body": ["url": huge]]) == .failure(.badBody))
    }

    @Test func onlyTheAppsOwnLinksOpen() {
        #expect(Relay.action(for: ["type": "open", "url": "videodownloader://inspect?url=https%3A%2F%2Fx.test"]) ==
            .success(.open(URL(string: "videodownloader://inspect?url=https%3A%2F%2Fx.test")!)))
        #expect(Relay.action(for: ["type": "open", "url": "videodownloader://show?route=download"]) != .failure(.notAllowed))
        for raw in ["https://evil.example/", "file:///Applications/Calculator.app", "videodownloader://format", "x-apple.systempreferences:"] {
            #expect(Relay.action(for: ["type": "open", "url": raw]) == .failure(.notAllowed), "\(raw)")
        }
    }

    @Test func repliesSayWhetherTheAppAnswered() {
        let offline = Relay.reply(data: nil, response: nil, error: URLError(.cannotConnectToHost))
        #expect(offline["offline"] as? Bool == true)
        let response = HTTPURLResponse(url: URL(string: "http://127.0.0.1:8787/api/jobs")!, statusCode: 400, httpVersion: nil, headerFields: nil)
        let refused = Relay.reply(data: Data(#"{"error":{"code":"OFFER_UNKNOWN"}}"#.utf8), response: response, error: nil)
        #expect(refused["ok"] as? Bool == false && refused["status"] as? Int == 400)
        #expect(((refused["json"] as? [String: Any])?["error"] as? [String: Any])?["code"] as? String == "OFFER_UNKNOWN")
    }
}

struct RelaySafetyTests {
    @Test func theExtensionCannotAimTheAppAtThisMacOrTheLAN() {
        for raw in ["http://127.0.0.1:8787/api/events", "http://192.168.1.1/cgi-bin/reboot", "http://localhost/",
                    "http://[::1]/", "http://router.local/", "http://10.0.0.2/", "file:///etc/passwd", "javascript:alert(1)"] {
            for path in ["api/inspect", "api/quick"] {
                #expect(Relay.action(for: ["type": "api", "method": "POST", "path": path, "body": ["url": raw]]) == .failure(.localAddress), "\(path) \(raw)")
            }
        }
        #expect(Relay.action(for: ["type": "api", "method": "POST", "path": "api/quick", "body": ["url": 42]]) == .failure(.localAddress))
        if case .failure = Relay.action(for: ["type": "api", "method": "POST", "path": "api/quick", "body": ["inspect_id": "x", "offer_id": "v1"]]) {
            Issue.record("a quick choice by inspect id carries no URL and must pass")
        }
    }

    @Test func aPlusInThePageAddressSurvivesTheTrip() throws {
        guard case .success(.http(let request)) = Relay.action(for: ["type": "api", "path": "api/supports", "query": ["url": "https://x.test/s?q=a+b&c=d"]]) else {
            Issue.record("refused")
            return
        }
        let query = try #require(request.url?.query(percentEncoded: true))
        #expect(query == "url=https://x.test/s%3Fq%3Da%2Bb%26c%3Dd")
        let decoded = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems?.first?.value
        #expect(decoded == "https://x.test/s?q=a+b&c=d")
    }
}
