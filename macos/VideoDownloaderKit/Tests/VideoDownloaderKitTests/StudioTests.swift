import CoreMedia
import Foundation
import Testing
@testable import VideoDownloaderKit

struct TimeGridTests {
    @Test func aVideoIsCutInItsOwnFrames() {
        let grid = TimeGrid(rate: FrameRate(num: 25, den: 1), duration: 4.0)
        #expect(grid.isFrames && grid.count == 100)
        #expect(grid.seconds(10) == 0.4)
        #expect(grid.position(0.41) == 10 && grid.position(0.43) == 11)
        #expect(grid.unit(containing: 0.439) == 10)  // the frame on screen at that moment
        #expect(grid.clamp(500) == 100 && grid.clamp(-3) == 0)
        #expect(grid.label(10) == "0:00.400")
    }

    /// 29.97 fps: frame times are not round milliseconds, and CMTime keeps them exact.
    @Test func aFractionalRateStaysExact() {
        let grid = TimeGrid(rate: FrameRate(num: 30000, den: 1001), duration: 10.01)
        #expect(grid.count == 300)
        #expect(grid.time(300) == CMTime(value: 300_300, timescale: 30000))
        // Seeking to the middle of a frame shows that frame whatever tiny offset the file has.
        #expect(abs(grid.middle(10).seconds - (10.5 * 1001 / 30000)) < 1e-9)
        for frame in [0, 1, 299, 150] { #expect(grid.position(grid.seconds(frame)) == frame) }
    }

    /// The picture starts 63 ms into the file: frame 0 is there on the player's clock, and the
    /// frame count leaves those 63 ms out.
    @Test func frameZeroIsTheVideosFirstFrame() {
        let grid = TimeGrid(rate: FrameRate(num: 25, den: 1), duration: 4.063, origin: 0.063)
        #expect(grid.count == 100)
        #expect(abs(grid.middle(10).seconds - (0.063 + 0.42)) < 1e-6)
        #expect(grid.unit(containing: 0.063 + 0.4 + 0.01) == 10)
        #expect(grid.unit(containing: 0.063 + 0.39) == 9)
        #expect(grid.label(10) == "0:00.400")  // labels count from the first frame
        #expect(TimeGrid(rate: nil, duration: 2, origin: 0.5).origin == 0)  // sound has no frame 0
    }

    @Test func soundIsCutInMilliseconds() {
        let grid = TimeGrid(rate: nil, duration: 2.5)
        #expect(!grid.isFrames && grid.count == 2500)
        #expect(grid.position(1.2345) == 1235 || grid.position(1.2345) == 1234)
        #expect(grid.label(61_005) == "1:01.005")
    }

    @Test func timesAreReadAsTheWebPageReadsThem() {
        #expect(TimeGrid.parse("90") == 90)
        #expect(TimeGrid.parse("1:30") == 90)
        #expect(TimeGrid.parse("1:02:03.5") == 3723.5)
        #expect(TimeGrid.parse("12,5") == 12.5)
        #expect(TimeGrid.parse("1:75") == nil)
        #expect(TimeGrid.parse("abc") == nil)
        #expect(TimeGrid.clock(3723.5) == "1:02:03.500")
    }

    @Test func aLosslessStartFindsTheNearestKeyframe() {
        let keys = [0, 25, 50, 75]
        #expect(nearestKeyframe(30, in: keys) == 25)
        #expect(nearestKeyframe(40, in: keys) == 50)
        #expect(nearestKeyframe(99, in: keys) == 75)
        #expect(nearestKeyframe(7, in: []) == 7)
        #expect(keyframe(before: 25, in: keys) == 0 && keyframe(after: 25, in: keys) == 50)
        #expect(keyframe(after: 75, in: keys) == nil)
    }
}

@MainActor
struct StudioRulesTests {
    static func video(chapters: [StudioChapter] = []) -> StudioSource {
        StudioSource(path: "/x/clip.mkv", name: "clip.mkv", ext: "mkv", size: 1000, duration: 4.0,
                     streams: [StudioStream(index: 0, type: "video", codec: "vp9", language: nil, title: nil, default: true,
                                            attachedPic: false, width: 640, height: 360, channels: nil),
                               StudioStream(index: 1, type: "audio", codec: "opus", language: "eng", title: nil, default: true,
                                            attachedPic: false, width: nil, height: nil, channels: 2)],
                     chapters: chapters, youtubeAutoCaptions: false,
                     frameRate: FrameRate(num: 25, den: 1), variableFrameRate: false)
    }

    func studio(_ source: StudioSource = video()) -> Studio {
        let studio = Studio(client: { APIClient(port: 1) })
        studio.start(with: source)
        return studio
    }

    @Test func aNewSourceStartsWithTheWholeFileAndAFittingName() {
        let studio = studio()
        #expect(studio.segments.map { [$0.start, $0.end] } == [[0, 100]])
        #expect(studio.operation == .trim && studio.trimMode == .accurate)
        #expect(studio.outputName == "clip \(L("studio.outputSuffix.trim"))")
        studio.operation = .audio
        #expect(studio.outputName == "clip \(L("studio.outputSuffix.audio"))")
        studio.outputName = "benim adım"
        studio.operation = .trim
        #expect(studio.outputName == "benim adım")  // typed: kept
    }

    @Test func handlesStayOnFramesAndNeverCross() {
        let studio = studio()
        studio.setStart(10)
        studio.setEnd(35)
        #expect(studio.current?.start == 10 && studio.current?.end == 35)
        studio.setStart(80)  // past the end: one frame before it
        #expect(studio.current?.start == 34)
        studio.setEnd(2)  // before the start: one frame after it
        #expect(studio.current?.end == 35)
        studio.nudgeEnd(1)
        #expect(studio.current?.end == 36)
    }

    @Test func theRequestCarriesFramesForVideo() throws {
        let studio = studio()
        studio.setStart(10)
        studio.setEnd(35)
        let body = try #require(studio.body)
        let options = try #require(body["options"] as? [String: any Sendable])
        let pieces = try #require(options["segments"] as? [[String: any Sendable]])
        #expect(pieces.first?["start_frame"] as? Int == 10 && pieces.first?["end_frame"] as? Int == 35)
        #expect(options["mode"] as? String == "accurate")
        #expect(studio.bodyKey != nil)
    }

    @Test func soundIsSentInSeconds() throws {
        var sound = Self.video()
        sound = StudioSource(path: "/x/a.m4a", name: "a.m4a", ext: "m4a", size: 10, duration: 2.0,
                             streams: [sound.streams[1]], chapters: [], youtubeAutoCaptions: false)
        let studio = studio(sound)
        studio.setStart(250)
        let options = try #require(studio.body?["options"] as? [String: any Sendable])
        let piece = try #require((options["segments"] as? [[String: any Sendable]])?.first)
        #expect(piece["start"] as? Double == 0.25 && piece["end"] as? Double == 2.0)
    }

    @Test func losslessStartsSnapToKeyframesAndStepBetweenThem() {
        let studio = studio()
        studio.setStart(30)
        studio.setEnd(90)
        studio.injectKeyframes([0, 25, 50, 75])
        studio.trimMode = .lossless
        #expect(studio.current?.start == 25)  // snapped when switching
        studio.setStart(41)
        #expect(studio.current?.start == 50)
        studio.nudgeStart(1)
        #expect(studio.current?.start == 75)
        studio.nudgeStart(1)  // no keyframe left before the end: stays
        #expect(studio.current?.start == 75)
        studio.trimMode = .accurate
        studio.setStart(41)
        #expect(studio.current?.start == 41)  // any frame again
    }

    @Test func piecesAndChapters() {
        let studio = studio(Self.video(chapters: [StudioChapter(start: 1, end: 2, title: "İkinci")]))
        studio.useChapter(studio.source!.chapters[0])
        #expect(studio.segments.map { [$0.start, $0.end] } == [[25, 50]])  // replaced the untouched whole file
        studio.addSegment()
        #expect(studio.segments.count == 2 && studio.active == 1 && studio.segments[1].start == 50)
        studio.removeSegment(at: 0)
        #expect(studio.segments.count == 1 && studio.active == 0)
        studio.removeSegment(at: 0)  // the last one stays
        #expect(studio.segments.count == 1)
    }

    @Test func remuxTracksMoveAndTheSubtitleOffsetMustBeANumber() {
        let studio = studio()
        #expect(studio.tracks.map(\.stream.index) == [0, 1])
        studio.moveTrack(1, by: -1)
        #expect(studio.tracks.map(\.stream.index) == [1, 0])
        studio.offset = "1,5"
        #expect(studio.offsetSeconds == 1.5)
        studio.offset = "-2"
        #expect(studio.offsetSeconds == -2)
        studio.offset = "iki"
        #expect(studio.offsetSeconds == nil)
    }

    @Test func theRulerNeverRoundsIntoTheNextSecond() {
        #expect(Ruler.label(0.5, tenths: true) == "0:00.5")
        #expect(Ruler.label(1.5, tenths: true) == "0:01.5")
        #expect(Ruler.label(65, tenths: false) == "1:05")
        #expect(Ruler.label(3725, tenths: false) == "1:02:05")
    }

    @Test func framesPerSecondReadAsPeopleSayThem() {
        #expect(Format.fps(FrameRate(num: 25, den: 1)) == "25")
        #expect(Format.fps(FrameRate(num: 30000, den: 1001)) == "29.97")
        #expect(Format.fps(FrameRate(num: 60000, den: 1001)) == "59.94")
    }
}
