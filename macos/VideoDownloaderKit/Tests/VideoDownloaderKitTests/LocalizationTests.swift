import Foundation
import Testing
@testable import VideoDownloaderKit

/// Every key the code asks for exists in the catalog: a missing one would show as ⟦key⟧.
struct LocalizationTests {
    static let sources = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .appending(path: "Sources/VideoDownloaderKit")

    @Test func everyKeyUsedInTheSourcesIsTranslated() throws {
        let catalog = try JSONSerialization.jsonObject(with: Data(contentsOf: Self.sources.appending(path: "Resources/Localizable.xcstrings"))) as? [String: Any]
        let keys = Set(((catalog?["strings"] as? [String: Any]) ?? [:]).keys)
        let pattern = try Regex(#"L\("([a-zA-Z0-9_.]+)""#)
        var used = Set<String>()
        let app = Self.sources.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appending(path: "VideoDownloader/VideoDownloader")
        let files = [Self.sources, app].flatMap {
            FileManager.default.enumerator(at: $0, includingPropertiesForKeys: nil)?
                .compactMap { $0 as? URL }.filter { $0.pathExtension == "swift" } ?? []
        }
        for file in files {
            for match in try String(contentsOf: file, encoding: .utf8).matches(of: pattern) {
                if let key = match.output[1].substring { used.insert(String(key)) }
            }
        }
        #expect(!used.isEmpty)
        #expect(used.subtracting(keys).sorted() == [])
        for key in used { #expect(!L(key).hasPrefix("⟦"), "\(key)") }
    }

    @Test func portsAndCodesAreNeverDigitGrouped() {
        #expect(L("backend.reason.portBusy", 8787).hasPrefix("8787 portunu"))
        #expect(L("backend.reason.exited", 1).contains("çıkış kodu 1"))
    }
}
