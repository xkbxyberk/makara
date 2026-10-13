import AppKit

/// A thin progress bar across the bottom of the Dock icon while something downloads (P6g), as
/// Finder and Safari show copies; the count stays in the badge.
@MainActor
final class DockProgress {
    private var bar: NSProgressIndicator?
    private var shown: Double?

    /// `fraction` of everything running, or nil to show the plain icon.
    func update(_ fraction: Double?) {
        guard let app = NSApp else { return }
        let tile = app.dockTile
        guard let fraction else {
            if shown != nil {
                tile.contentView = nil
                bar = nil
                shown = nil
                tile.display()
            }
            return
        }
        // Redraw only for a visible change (the Dock is not free to repaint).
        if let shown, abs(shown - fraction) < 0.005 { return }
        if bar == nil {
            let size = tile.size
            let icon = NSImageView(frame: NSRect(origin: .zero, size: size))
            icon.image = app.applicationIconImage
            let progress = NSProgressIndicator(frame: NSRect(x: size.width * 0.14, y: size.height * 0.1,
                                                             width: size.width * 0.72, height: max(10, size.height * 0.1)))
            progress.style = .bar
            progress.isIndeterminate = false
            progress.minValue = 0
            progress.maxValue = 1
            icon.addSubview(progress)
            tile.contentView = icon
            bar = progress
        }
        bar?.doubleValue = fraction
        shown = fraction
        tile.display()
    }
}
