import Testing
@testable import VideoDownloaderKit

struct SSEParserTests {
    /// Split on the newline *byte*, as EventStream does ("\r\n" is one Character in Swift).
    func parse(_ text: String) -> [(String, String)] {
        var parser = SSEParser()
        return Array(text.utf8).split(separator: UInt8(ascii: "\n"), omittingEmptySubsequences: false).compactMap {
            parser.feed(line: String(decoding: $0, as: UTF8.self)).map { ($0.name, $0.data) }
        }
    }

    @Test func dispatchesOnBlankLinesAndSkipsCommentsAndRetry() {
        let events = parse("retry: 2000\n\nevent: snapshot\ndata: []\n\n: keepalive\n\nevent: job\ndata: {\"a\":1}\n\n")
        #expect(events.map(\.0) == ["snapshot", "job"])
        #expect(events.map(\.1) == ["[]", "{\"a\":1}"])
    }

    @Test func joinsMultiLineDataAndHandlesCRLF() {
        let events = parse("data: one\r\ndata: two\r\n\r\n")
        #expect(events.count == 1)
        #expect(events.first?.0 == "message")
        #expect(events.first?.1 == "one\ntwo")
    }

    @Test func aFieldWithoutASpaceAfterTheColonStillParses() {
        #expect(parse("event:removed\ndata:{\"id\":\"x\"}\n\n").first?.0 == "removed")
    }

    @Test func unknownEventsAreKeptNotDropped() {
        #expect(ServerEvent.decode(name: "something_new", data: "{}") == .other("something_new"))
        #expect(ServerEvent.decode(name: "removed", data: #"{"type":"removed","id":"ab"}"#) == .removed("ab"))
        #expect(ServerEvent.decode(name: "clipboard", data: #"{"type":"clipboard","url":"https://x.test/v"}"#) == .clipboard("https://x.test/v"))
    }
}
