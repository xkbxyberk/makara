import Foundation
import SafariServices
import os

/// The extension's native half. The page-side JavaScript never talks to the backend directly:
/// it sends a message here, and this sandboxed handler (outgoing connections only) asks the
/// local backend on 127.0.0.1 and answers.
final class SafariWebExtensionHandler: NSObject, NSExtensionRequestHandling {
    private static let log = Logger(subsystem: "com.berkakbay.VideoDownloader", category: "extension")
    private static let backend = URL(string: "http://127.0.0.1:8787")!

    func beginRequest(with context: NSExtensionContext) {
        let item = context.inputItems.first as? NSExtensionItem
        let message = item?.userInfo?[SFExtensionMessageKey] as? [String: Any] ?? [:]
        let type = message["type"] as? String ?? "?"

        switch type {
        case "ping":
            Self.log.notice("ping (\(message["reason"] as? String ?? "?", privacy: .public))")
            health(stage: "ping") { reply in
                Self.log.notice("health -> \(String(describing: reply), privacy: .public)")
                Self.complete(context, with: reply)
            }
        case "report":
            // The background script echoes what it received: proof of the full round trip.
            let reply = message["reply"] as? [String: Any]
            Self.log.notice("round trip complete: \(String(describing: reply), privacy: .public)")
            // N0 spike: tell the backend too, so the round trip shows up in its access log.
            health(stage: "report-\((reply?["ok"] as? Bool) == true ? "ok" : "failed")") { _ in
                Self.complete(context, with: ["logged": true])
            }
        default:
            Self.complete(context, with: ["error": "UNKNOWN_MESSAGE"])
        }
    }

    private func health(stage: String, _ done: @escaping ([String: Any]) -> Void) {
        let url = Self.backend.appending(path: "api/health")
            .appending(queryItems: [URLQueryItem(name: "from", value: "safari-extension"), URLQueryItem(name: "stage", value: stage)])
        var request = URLRequest(url: url)
        request.timeoutInterval = 3
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error {
                done(["ok": false, "error": error.localizedDescription])
                return
            }
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            let body = data.flatMap { String(data: $0, encoding: .utf8) } ?? ""
            done(["ok": status == 200, "status": status, "body": body])
        }.resume()
    }

    private static func complete(_ context: NSExtensionContext, with reply: [String: Any]) {
        let response = NSExtensionItem()
        response.userInfo = [SFExtensionMessageKey: reply]
        context.completeRequest(returningItems: [response], completionHandler: nil)
    }
}
