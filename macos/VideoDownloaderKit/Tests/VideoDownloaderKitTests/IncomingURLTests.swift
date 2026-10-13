import Foundation
import Testing
@testable import VideoDownloaderKit

struct IncomingURLTests {
    @Test func aWebLinkIsInspected() {
        let url = URL(string: "https://www.youtube.com/watch?v=xnP7qKxwzjg")!
        #expect(IncomingURL.parse(url) == .inspect(url))
    }

    @Test func theURLSchemeCarriesAnEncodedLink() {
        let url = URL(string: "videodownloader://inspect?url=https%3A%2F%2Fvimeo.com%2F76979871%3Fa%3D1%26b%3D2")!
        #expect(IncomingURL.parse(url) == .inspect(URL(string: "https://vimeo.com/76979871?a=1&b=2")!))
    }

    @Test func theSchemeNeverInspectsANonWebLink() {
        for raw in ["videodownloader://inspect?url=file%3A%2F%2F%2Fetc%2Fpasswd",
                    "videodownloader://inspect?url=javascript%3Aalert(1)",
                    "videodownloader://inspect",
                    "videodownloader://format-disk"] {
            #expect(IncomingURL.parse(URL(string: raw)!) == nil, "\(raw)")
        }
        #expect(IncomingURL.parse(URL(string: "ftp://example.com/x")!) == nil)
    }

    @Test func showOpensAScreen() {
        #expect(IncomingURL.parse(URL(string: "videodownloader://show?route=library")!) == .show(.library))
        #expect(IncomingURL.parse(URL(string: "videodownloader://show")!) == .show(nil))
        #expect(IncomingURL.parse(URL(string: "videodownloader://show?route=nonsense")!) == .show(nil))
    }

    @Test func aWeblocFileIsReadForItsLink() throws {
        let plist = try PropertyListSerialization.data(fromPropertyList: ["URL": "https://example.com/v"], format: .xml, options: 0)
        let file = URL(fileURLWithPath: "/tmp/link.webloc")
        #expect(IncomingURL.parse(file, readFile: { _ in plist }) == .inspect(URL(string: "https://example.com/v")!))
        let bad = try PropertyListSerialization.data(fromPropertyList: ["URL": "file:///etc/passwd"], format: .xml, options: 0)
        #expect(IncomingURL.parse(file, readFile: { _ in bad }) == nil)
        #expect(IncomingURL.parse(URL(fileURLWithPath: "/tmp/movie.mp4"), readFile: { _ in Data() }) == nil)
    }
}

struct IncomingURLSafetyTests {
    @Test func thisMacAndTheLocalNetworkAreNeverInspected() {
        for raw in ["http://127.0.0.1:8787/api/events", "http://localhost/x", "http://192.168.1.1/admin",
                    "http://10.0.0.5/", "http://172.20.1.1/", "http://169.254.169.254/latest", "http://[::1]/",
                    "http://router.local/", "http://intranet/", "http://100.64.0.1/", "http://0.0.0.0/"] {
            #expect(IncomingURL.parse(URL(string: raw)!) == nil, "\(raw)")
            let wrapped = "videodownloader://inspect?url=" + raw.addingPercentEncoding(withAllowedCharacters: .alphanumerics)!
            #expect(IncomingURL.parse(URL(string: wrapped)!) == nil, "\(wrapped)")
        }
        #expect(IncomingURL.parse(URL(string: "https://172.32.0.1/")!) != nil)  // just outside 172.16/12
        #expect(IncomingURL.parse(URL(string: "https://www.youtube.com/watch?v=x")!) != nil)
    }

    @Test func aWeblocPointingAtAnotherFileIsRefusedNotFollowed() throws {
        // It used to recurse into itself until the stack overflowed.
        let file = URL(fileURLWithPath: "/tmp/self.webloc")
        let loop = try PropertyListSerialization.data(fromPropertyList: ["URL": file.absoluteString], format: .xml, options: 0)
        #expect(IncomingURL.parse(file, readFile: { _ in loop }) == nil)
        let local = try PropertyListSerialization.data(fromPropertyList: ["URL": "http://127.0.0.1:8787/"], format: .xml, options: 0)
        #expect(IncomingURL.parse(file, readFile: { _ in local }) == nil)
    }

}
