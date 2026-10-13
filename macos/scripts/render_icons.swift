// Renders the extension's icons from SF Symbols, so they match the system exactly.
// Usage: swift macos/scripts/render_icons.swift <output dir>
import AppKit

let out = URL(fileURLWithPath: CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : ".")

func render(_ symbol: String, size: Int, color: NSColor, background: NSColor?, name: String) throws {
    let px = CGFloat(size)
    let image = NSImage(size: NSSize(width: px, height: px), flipped: false) { rect in
        if let background {
            background.setFill()
            NSBezierPath(roundedRect: rect, xRadius: px * 0.225, yRadius: px * 0.225).fill()
        }
        let pointSize = background == nil ? px * 0.82 : px * 0.58
        let config = NSImage.SymbolConfiguration(pointSize: pointSize, weight: .semibold)
            .applying(.init(paletteColors: [color]))
        guard let glyph = NSImage(systemSymbolName: symbol, accessibilityDescription: nil)?
            .withSymbolConfiguration(config) else { return false }
        let g = glyph.size
        glyph.draw(in: NSRect(x: (px - g.width) / 2, y: (px - g.height) / 2, width: g.width, height: g.height))
        return true
    }
    guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
                                     bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                     colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { return }
    rep.size = NSSize(width: px, height: px)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    image.draw(in: NSRect(x: 0, y: 0, width: px, height: px))
    NSGraphicsContext.restoreGraphicsState()
    try rep.representation(using: .png, properties: [:])!.write(to: out.appendingPathComponent(name))
}

let accent = NSColor(srgbRed: 0, green: 0.478, blue: 1, alpha: 1)
for size in [48, 96, 128, 256, 512] {
    try render("arrow.down", size: size, color: .white, background: accent, name: "icon-\(size).png")
}
// Toolbar icons are templates: Safari tints them, so they are drawn in black on transparent.
for size in [16, 32] {
    // Idle: an outline. Something to download on this page: the filled symbol.
    try render("arrow.down.circle", size: size, color: .black, background: nil, name: "toolbar-\(size).png")
    try render("arrow.down.circle.fill", size: size, color: .black, background: nil, name: "toolbar-active-\(size).png")
}
