// swift-tools-version: 6.2
import PackageDescription

// Everything of the native app that can be tested from the command line (`swift test`):
// API models and client, the SSE reader, the backend launcher, app state and the SwiftUI views.
// The Xcode project only holds the app and Safari extension targets.
let package = Package(
    name: "VideoDownloaderKit",
    defaultLocalization: "tr",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "VideoDownloaderKit", targets: ["VideoDownloaderKit"]),
        // The Safari extension's native half links only this: small, no UI, no resources.
        .library(name: "VideoDownloaderRelay", targets: ["VideoDownloaderRelay"]),
    ],
    targets: [
        .target(name: "VideoDownloaderKit", dependencies: ["VideoDownloaderRelay"], resources: [.process("Resources")]),
        .target(name: "VideoDownloaderRelay"),
        .testTarget(name: "VideoDownloaderKitTests", dependencies: ["VideoDownloaderKit"]),
        .testTarget(name: "VideoDownloaderRelayTests", dependencies: ["VideoDownloaderRelay"]),
    ]
)
