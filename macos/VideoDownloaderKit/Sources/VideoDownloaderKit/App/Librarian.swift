import Foundation
import Observation

/// Kütüphane's state, kept by the app model so the filters and the selection survive a trip to
/// another screen (the native twin of the web page's LibraryRoute).
@MainActor
@Observable
public final class Librarian {
    public enum Layout: String, CaseIterable, Sendable { case grid, list }

    public enum Phase: Equatable {
        case loading
        case failed(APIError)
        case ready(LibraryPage)
    }

    public enum Scan: Equatable {
        case idle, running
        case done(ScanResult)
    }

    public var query = LibraryQuery()
    public var layout: Layout {
        didSet { store.set(layout.rawValue, Self.layoutKey) }
    }
    public private(set) var phase: Phase = .loading
    public var selection: LibraryItem.ID?
    public private(set) var scan: Scan = .idle
    /// The last action that failed (play, reveal, trash, scan), as a code.
    public var actionError: String?
    /// The item whose Trash confirmation is on screen.
    public var confirming: LibraryItem?
    /// Bumped by the server's `library` event: something was added or changed.
    public private(set) var version = 0

    static let layoutKey = "vd-library-view"
    @ObservationIgnored private let client: () -> APIClient
    @ObservationIgnored private let store: LocalStore
    @ObservationIgnored private var ticket = 0

    public init(client: @escaping () -> APIClient, store: LocalStore) {
        self.client = client
        self.store = store
        layout = store.string(Self.layoutKey).flatMap(Layout.init(rawValue:)) ?? .grid
    }

    public var page: LibraryPage? {
        if case .ready(let page) = phase { return page }
        return nil
    }

    public var selectedItem: LibraryItem? { page?.items.first { $0.id == selection } }

    /// What the view's reload task depends on: the query, and the server saying "changed".
    public struct Trigger: Hashable { let query: LibraryQuery; let version: Int }
    public var trigger: Trigger { Trigger(query: query, version: version) }

    func changed() { version += 1 }

    /// The newest request wins; an older, slower answer is dropped.
    public func load() async {
        ticket += 1
        let mine = ticket
        let asked = query
        let outcome: Phase
        do {
            outcome = .ready(try await client().library(asked))
        } catch {
            if Task.isCancelled { return }
            outcome = .failed(APIError.from(error))
        }
        guard mine == ticket else { return }
        phase = outcome
        // A selection that is no longer listed (trashed, filtered out) closes the inspector; a
        // failed reload keeps it, to come back with the next answer.
        if case .ready(let page) = outcome, let selection, !page.items.contains(where: { $0.id == selection }) {
            self.selection = nil
        }
    }

    public func runScan() async {
        scan = .running
        do {
            scan = .done(try await client().scanLibrary())
            await load()
        } catch {
            scan = .idle
            actionError = APIError.from(error).code
        }
    }

    public func perform(_ action: @Sendable (APIClient) async throws -> Void) async {
        actionError = nil
        do { try await action(client()) } catch { actionError = APIError.from(error).code }
    }

    /// After Berk confirmed: the item's files go to the Trash, never deleted outright. The item
    /// comes from the dialog itself: dismissing it clears `confirming` before the button's
    /// action runs, so reading it here found nothing and the confirmation did nothing.
    public func trash(_ item: LibraryItem) async {
        confirming = nil
        actionError = nil
        do {
            try await client().trash(item: item.id)
            selection = nil
            await load()
        } catch {
            actionError = APIError.from(error).code
        }
    }
}
