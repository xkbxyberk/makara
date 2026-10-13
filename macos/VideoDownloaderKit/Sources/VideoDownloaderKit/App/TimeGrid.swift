import CoreMedia
import Foundation

/// The units a cut is chosen in: the source's own frames for a video (so a selection can only
/// ever sit on a frame boundary), milliseconds for sound. Position `n` is the boundary before
/// unit `n`; a range [start, end) keeps units start ..< end.
public struct TimeGrid: Sendable, Equatable {
    public let rate: FrameRate?
    /// How many units the source has (frames, or milliseconds).
    public let count: Int
    /// Where position 0 is on the player's clock (the first video frame; 0 for sound).
    public let origin: Double

    public init(rate: FrameRate?, duration: Double, origin: Double = 0) {
        self.rate = rate
        self.origin = rate == nil ? 0 : max(0, origin)
        if let rate {
            count = max(1, Int(((duration - self.origin) * rate.perSecond).rounded()))
        } else {
            count = max(1, Int((duration * 1000).rounded()))
        }
    }

    public var isFrames: Bool { rate != nil }

    /// The length of one unit, in seconds.
    public var unit: Double { rate?.seconds ?? 0.001 }

    public func seconds(_ position: Int) -> Double { Double(position) * unit }

    /// The boundary nearest to a time.
    public func position(_ seconds: Double) -> Int { clamp(Int((seconds / unit).rounded())) }

    /// The unit (frame) a player time falls in.
    public func unit(containing seconds: Double) -> Int {
        clamp(Int(((seconds - origin) / unit + 1e-6).rounded(.down)), upper: count - 1)
    }

    public func clamp(_ position: Int, upper: Int? = nil) -> Int { min(max(0, position), upper ?? count) }

    /// Exact player times: the start of a unit, and its middle (seeking to the middle shows that
    /// frame whatever tiny offset the file's timestamps carry).
    /// The player time where a unit starts (the origin plus an exact rational offset).
    public func time(_ position: Int) -> CMTime {
        if let rate {
            let offset = CMTime(value: CMTimeValue(position) * CMTimeValue(rate.den), timescale: CMTimeScale(rate.num))
            return CMTimeAdd(CMTime(seconds: origin, preferredTimescale: 1_000_000), offset)
        }
        return CMTime(value: CMTimeValue(position), timescale: 1000)
    }

    public func middle(_ position: Int) -> CMTime {
        if let rate {
            let offset = CMTime(value: CMTimeValue(position) * 2 * CMTimeValue(rate.den) + CMTimeValue(rate.den),
                                timescale: CMTimeScale(rate.num) * 2)
            return CMTimeAdd(CMTime(seconds: origin, preferredTimescale: 1_000_000), offset)
        }
        return CMTime(value: CMTimeValue(position) * 2 + 1, timescale: 2000)
    }

    /// "1:02.345", or "1:02:03.345" past an hour (what the fields show and accept).
    public func label(_ position: Int) -> String { Self.clock(seconds(position)) }

    public static func clock(_ seconds: Double) -> String {
        let ms = Int((seconds * 1000).rounded())
        let (h, m, s, f) = (ms / 3_600_000, ms % 3_600_000 / 60000, ms % 60000 / 1000, ms % 1000)
        return h > 0 ? String(format: "%d:%02d:%02d.%03d", h, m, s, f) : String(format: "%d:%02d.%03d", m, s, f)
    }

    /// "90", "1:30", "1:02:03.5", "12,5" -> seconds; nil when it is not a time (as `parseTime`).
    public static func parse(_ text: String) -> Double? {
        let value = text.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: ".")
        guard value.wholeMatch(of: /\d+(:\d{1,2}){0,2}(\.\d+)?/) != nil else { return nil }
        let parts = value.split(separator: ":").map { Double($0) ?? 0 }
        guard parts.dropFirst().allSatisfy({ $0 < 60 }) else { return nil }
        return parts.reduce(0) { $0 * 60 + $1 }
    }

    /// Keyframe times as positions, each once, in order.
    public func positions(of times: [Double]) -> [Int] {
        Array(Set(times.map(position))).sorted()
    }
}

/// One piece to keep, in grid positions: [start, end).
public struct TrimSegment: Identifiable, Sendable, Equatable, Hashable {
    public let id: UUID
    public var start: Int
    public var end: Int

    public init(start: Int, end: Int, id: UUID = UUID()) {
        self.id = id
        self.start = start
        self.end = end
    }

    public var length: Int { end - start }
}

/// Where a lossless cut may start: the keyframe nearest to the position asked for.
public func nearestKeyframe(_ position: Int, in keyframes: [Int]) -> Int {
    guard !keyframes.isEmpty else { return position }
    // Binary search for the first keyframe after `position`.
    var low = 0
    var high = keyframes.count
    while low < high {
        let mid = (low + high) / 2
        if keyframes[mid] <= position { low = mid + 1 } else { high = mid }
    }
    let before = low > 0 ? keyframes[low - 1] : nil
    let after = low < keyframes.count ? keyframes[low] : nil
    switch (before, after) {
    case let (b?, a?): return position - b <= a - position ? b : a
    case let (b?, nil): return b
    case let (nil, a?): return a
    default: return position
    }
}

/// The keyframe strictly before / after a position (⌥← / ⌥→).
public func keyframe(before position: Int, in keyframes: [Int]) -> Int? { keyframes.last { $0 < position } }
public func keyframe(after position: Int, in keyframes: [Int]) -> Int? { keyframes.first { $0 > position } }
