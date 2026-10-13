@preconcurrency import AVFoundation
import AppKit
import Observation

/// The Stüdyo preview: macOS's own player on the source (when AVFoundation can step through it)
/// or on the backend's preview copy (preview.py: same frames, same timestamps), plus the
/// filmstrip under the timeline. Every seek is exact (zero tolerance) and aims at the middle of
/// a frame, so the picture is always the frame the timeline names.
@MainActor
@Observable
public final class PreviewPlayer {
    public enum Phase: Equatable {
        case none
        /// The backend is making a playable copy (0...1).
        case preparing(Double)
        case ready
        case failed(String)
    }

    public private(set) var phase: Phase = .none
    public let player = AVPlayer()
    /// The frame (or millisecond) under the playhead.
    public private(set) var position = 0
    public private(set) var isPlaying = false
    public private(set) var filmstrip: [CGImage] = []

    @ObservationIgnored private var grid = TimeGrid(rate: nil, duration: 1)
    @ObservationIgnored private var observer: Any?
    @ObservationIgnored private var task: Task<Void, Never>?
    @ObservationIgnored private var asset: AVURLAsset?
    @ObservationIgnored private var stripTask: Task<Void, Never>?
    @ObservationIgnored private var stripCount = 0
    @ObservationIgnored private var seeking = false
    @ObservationIgnored private var status: NSKeyValueObservation?

    public init() {
        player.actionAtItemEnd = .pause
        player.preventsDisplaySleepDuringVideoPlayback = true
    }

    /// Show `source`: directly when the system player can step through it, else through the
    /// backend's preview copy (made once and cached).
    public func load(_ source: StudioSource, grid: TimeGrid, client: APIClient) {
        task?.cancel()
        stripTask?.cancel()
        self.grid = grid
        position = 0
        filmstrip = []
        stripCount = 0
        asset = nil  // the filmstrip must never be made from the previous source
        status = nil
        player.pause()
        player.replaceCurrentItem(with: nil)
        guard source.hasMedia else {
            phase = .none
            return
        }
        phase = .preparing(0)
        task = Task { [weak self] in
            let direct = URL(fileURLWithPath: source.path)
            let plays = await Self.playsDirectly(direct, video: source.hasVideo)
            // Another source may have been opened while this one was being looked at.
            guard !Task.isCancelled else { return }
            if plays {
                self?.attach(direct)
                return
            }
            do {
                var status = try await client.startPreview(path: source.path)
                while status.state == "running" {
                    self?.phase = .preparing(status.progress)
                    try await Task.sleep(for: .milliseconds(300))
                    status = try await client.preview(path: source.path)
                }
                guard !Task.isCancelled else { return }
                if status.state == "ready", let path = status.path, FileManager.default.fileExists(atPath: path) {
                    self?.attach(URL(fileURLWithPath: path))
                } else {
                    self?.phase = .failed(status.error ?? "PREVIEW_FAILED")
                }
            } catch {
                if !Task.isCancelled { self?.phase = .failed(APIError.from(error).code) }
            }
        }
    }

    /// MP4/MOV/M4A with H.264/HEVC (or sound AVFoundation decodes): measured to step through
    /// reliably. Everything else goes through the preview copy.
    nonisolated static func playsDirectly(_ url: URL, video: Bool) async -> Bool {
        guard ["mp4", "m4v", "mov", "m4a", "mp3", "aac", "wav", "aiff"].contains(url.pathExtension.lowercased()) else { return false }
        let asset = AVURLAsset(url: url)
        guard (try? await asset.load(.isPlayable)) == true else { return false }
        guard video else { return true }
        guard let track = try? await asset.loadTracks(withMediaType: .video).first,
              let formats = try? await track.load(.formatDescriptions), let format = formats.first else { return false }
        let codec = CMFormatDescriptionGetMediaSubType(format)
        return [kCMVideoCodecType_H264, kCMVideoCodecType_HEVC].contains(codec)
    }

    private func attach(_ url: URL) {
        let asset = AVURLAsset(url: url, options: [AVURLAssetPreferPreciseDurationAndTimingKey: true])
        self.asset = asset
        let item = AVPlayerItem(asset: asset)
        // A copy that cannot be read after all (deleted meanwhile, damaged) says so instead of
        // staying black with the controls enabled.
        status = item.observe(\.status) { [weak self] item, _ in
            guard item.status == .failed else { return }
            Task { @MainActor in self?.phase = .failed("PREVIEW_FAILED") }
        }
        player.replaceCurrentItem(with: item)
        if let observer { player.removeTimeObserver(observer) }
        let interval = CMTime(value: 1, timescale: 60)
        observer = player.addPeriodicTimeObserver(forInterval: interval, queue: .main) { [weak self] time in
            MainActor.assumeIsolated {
                guard let self, !self.seeking else { return }
                self.position = self.grid.unit(containing: time.seconds)
                self.isPlaying = self.player.timeControlStatus == .playing
            }
        }
        phase = .ready
        seek(to: 0)
    }

    // ---- control ------------------------------------------------------------------------------

    /// Show exactly this frame (or millisecond).
    public func seek(to position: Int) {
        let target = grid.clamp(position, upper: grid.count - 1)
        self.position = target
        guard player.currentItem != nil else { return }
        seeking = true
        player.seek(to: grid.middle(target), toleranceBefore: .zero, toleranceAfter: .zero) { [weak self] _ in
            MainActor.assumeIsolated { self?.seeking = false }
        }
    }

    public func step(_ by: Int) {
        pause()
        seek(to: position + by)
    }

    public func togglePlay(from start: Int? = nil) {
        if player.timeControlStatus == .playing {
            pause()
        } else {
            if let start, position >= grid.count - 1 { seek(to: start) }
            player.play()
            isPlaying = true
        }
    }

    public func pause() {
        player.pause()
        isPlaying = false
    }

    // ---- the filmstrip ------------------------------------------------------------------------

    /// About `count` pictures spread over the whole file (made again only when the count changes).
    public func makeFilmstrip(count: Int, height: CGFloat) {
        guard phase == .ready, let asset, count > 0, count != stripCount else { return }
        stripCount = count
        stripTask?.cancel()
        let duration = grid.seconds(grid.count)
        stripTask = Task { [weak self] in
            let generator = AVAssetImageGenerator(asset: asset)
            generator.appliesPreferredTrackTransform = true
            generator.maximumSize = CGSize(width: height * 4, height: height * 2)
            generator.requestedTimeToleranceBefore = CMTime(value: 1, timescale: 2)
            generator.requestedTimeToleranceAfter = CMTime(value: 1, timescale: 2)
            let times = (0..<count).map { CMTime(seconds: duration * (Double($0) + 0.5) / Double(count), preferredTimescale: 600) }
            var images: [CGImage] = []
            for await result in generator.images(for: times) {
                if Task.isCancelled { return }
                if let image = try? result.image { images.append(image) }
            }
            self?.filmstrip = images
        }
    }
}
