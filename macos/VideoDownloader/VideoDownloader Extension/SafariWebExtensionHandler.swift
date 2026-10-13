import AppKit
import Foundation
import SafariServices
import VideoDownloaderRelay

/// The extension's native half. The extension's JavaScript never talks to the backend itself:
/// it sends a message here, and this sandboxed handler (outgoing connections only) performs
/// one of the few requests `Relay` allows against 127.0.0.1, or opens a `videodownloader://`
/// link, and answers with the result.
final class SafariWebExtensionHandler: NSObject, NSExtensionRequestHandling {
    /// No cache, no cookies, nothing on disk: these requests carry the addresses of the pages
    /// Berk visits, and the shared session would keep them in a Cache.db (review finding).
    private static let session: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.urlCache = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        configuration.httpCookieStorage = nil
        return URLSession(configuration: configuration)
    }()

    func beginRequest(with context: NSExtensionContext) {
        let item = context.inputItems.first as? NSExtensionItem
        let message = item?.userInfo?[SFExtensionMessageKey] as? [String: Any] ?? [:]

        switch Relay.action(for: message) {
        case .failure(let refusal):
            Self.complete(context, with: ["ok": false, "refused": refusal.rawValue])
        case .success(.open(let url)):
            let opened = NSWorkspace.shared.open(url)
            Self.complete(context, with: ["ok": opened])
        case .success(.http(let request)):
            Self.session.dataTask(with: request) { data, response, error in
                Self.complete(context, with: Relay.reply(data: data, response: response, error: error))
            }.resume()
        }
    }

    private static func complete(_ context: NSExtensionContext, with reply: [String: Any]) {
        let response = NSExtensionItem()
        response.userInfo = [SFExtensionMessageKey: reply]
        context.completeRequest(returningItems: [response], completionHandler: nil)
    }
}
