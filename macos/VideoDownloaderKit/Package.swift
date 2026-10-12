// swift-tools-version: 6.2
import PackageDescription

// Everything of the native app that can be tested from the command line (`swift test`):
// API models and client, the SSE reader, the backend launcher, app state and the SwiftUI views.
// The Xcode project only holds the app and Safari extension targets.
let package = Package(
    name: "VideoDownloaderKit",
    defaultLocalization: "tr",
    platforms: [.macOS("27.0")],
    products: [.library(name: "VideoDownloaderKit", targets: ["VideoDownloaderKit"])],
    targets: [
        .target(name: "VideoDownloaderKit", resources: [.process("Resources")]),
        .testTarget(name: "VideoDownloaderKitTests", dependencies: ["VideoDownloaderKit"]),
    ]
)
