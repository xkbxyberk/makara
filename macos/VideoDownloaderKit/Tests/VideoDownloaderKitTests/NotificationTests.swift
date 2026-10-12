import Foundation
import Testing
@testable import VideoDownloaderKit

struct NotificationTests {
    func job(_ status: String, title: String? = "Clip") throws -> Job {
        let json = """
        {"id":"j","kind":"download","status":"\(status)","title":\(title.map { "\"\($0)\"" } ?? "null"),"output_files":[]}
        """
        return try JSON.decoder.decode(Job.self, from: Data(json.utf8))
    }

    @Test func aLiveFinishInTheBackgroundNotifies() throws {
        #expect(JobNotification.for(previous: try job("running"), current: try job("done"), appIsActive: false, enabled: true) == .done(title: "Clip"))
        #expect(JobNotification.for(previous: try job("running"), current: try job("failed"), appIsActive: false, enabled: true) == .failed(title: "Clip"))
    }

    @Test func nothingWhenInFrontDisabledAlreadySeenOrNotTerminal() throws {
        let running = try job("running"), done = try job("done")
        #expect(JobNotification.for(previous: running, current: done, appIsActive: true, enabled: true) == nil)
        #expect(JobNotification.for(previous: running, current: done, appIsActive: false, enabled: false) == nil)
        #expect(JobNotification.for(previous: nil, current: done, appIsActive: false, enabled: true) == nil)
        #expect(JobNotification.for(previous: done, current: done, appIsActive: false, enabled: true) == nil)
        #expect(JobNotification.for(previous: try job("queued"), current: running, appIsActive: false, enabled: true) == nil)
        #expect(JobNotification.for(previous: running, current: try job("cancelled"), appIsActive: false, enabled: true) == nil)
    }
}
